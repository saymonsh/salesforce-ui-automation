"""Smart-paste parser (issue #17, epic #14 step 3).

Turns a TAB/newline-separated clipboard block — copied straight out of Excel or
Google Sheets — into the in-memory shapes the manual-entry grid (#16) already
uses. This is **pure** text→data logic: no Flet, no clipboard I/O, no mutable
state, so it is trivially testable and the grid just hands it a string.

It also owns the validation primitives the grid renders against (``id_valid`` /
``type_valid`` / the date & time regexes), so the paste path and the typed path
judge a cell *identically* — a row that pastes in red is exactly a row the user
would have typed in red.

Two shapes, matching the grid's two families:

  * **tabular** (TYPE 1 / 2) → :func:`parse_tabular`: a list of
    ``{"id","type","date"}`` row dicts. An optional header row is auto-detected
    (Hebrew names or common aliases) and columns are mapped by name; with no
    header, columns map by position to the TYPE's natural order. Missing/extra
    columns are reported, never fatal.
  * **matrix** (TYPE 3) → :func:`parse_matrix`: ``HH:MM|HH:MM`` times in the
    top-left cell, dates across the rest of the first row, IDs down the first
    column, any non-empty body cell = present — the attendance-sheet convention.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

# Hebrew column keys the processors read — accessed by literal string.
COL_ID = "תעודות זהות"
COL_TYPE = "סוג"
COL_DATE = "תאריך"

# Attendance cell statuses the TYPE 3 matrix carries.
PRESENT = "נוכח"
ABSENT = "לא נוכח"

# TYPE 1 date is sent verbatim into the Salesforce field — accept the common
# Israeli D/M/Y (any of / . -) or an ISO date; kept lenient on purpose.
RE_LOOSE_DATE = re.compile(r"^(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{4}-\d{2}-\d{2})$")
RE_TIME = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def id_valid(value: str) -> bool:
    """Digits-only, 1–9 chars — lenient (no Israeli check-digit)."""
    s = (value or "").strip()
    return s.isdigit() and 1 <= len(s) <= 9


def type_valid(value: str) -> bool:
    s = (value or "").strip()
    return s.isdigit() and 1 <= int(s) <= 6


# Date styles accepted for a TYPE 3 matrix column and normalized to ISO. The
# Israeli day-first styles (d.m.y / d/m/y / d-m-y, 2- or 4-digit year) plus ISO
# itself — day-first, matching the Israeli date convention.
_DATE_INPUT_FORMATS = (
    "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y",
    "%d.%m.%y", "%d/%m/%y", "%d-%m-%y",
)


def _parse_date(value: str) -> datetime | None:
    s = (value or "").strip()
    if not s:
        return None
    for fmt in _DATE_INPUT_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def normalize_display_date(value: str) -> str | None:
    """Return ``value`` as Israeli ``d.m.yyyy`` for display, or ``None``. This is
    the canonical form the TYPE 3 grid *shows and stores* — the user thinks in
    day-first dates with no leading zeros. Built manually (not ``strftime``)
    because the no-pad directive ``%-d`` is not portable to Windows."""
    dt = _parse_date(value)
    return f"{dt.day}.{dt.month}.{dt.year}" if dt else None


def normalize_iso_date(value: str) -> str | None:
    """Return ``value`` as ISO ``yyyy-mm-dd``, or ``None``. This is the form the
    matrix is *handed to the processor* in (AttendanceProcessor parses
    ``"%Y-%m-%d %H:%M"``) — the conversion happens at the source boundary."""
    dt = _parse_date(value)
    return dt.strftime("%Y-%m-%d") if dt else None


# --------------------------------------------------------------------- headers
# Human label per field, for the missing/extra-column warnings.
_FIELD_LABEL = {"id": COL_ID, "type": COL_TYPE, "date": COL_DATE}

# Accepted header spellings → field. Normalized (see _norm) before lookup, so
# punctuation/case/spacing variants all collapse onto one key.
_HEADER_ALIASES = {
    "id": (COL_ID, "תעודת זהות", "תז", "ת.ז", "ת.ז.", "מספר זהות", "מספר ת.ז",
           "תעודת זיהוי", "id", "id number", "idnumber"),
    "type": (COL_TYPE, "סוג פעולה", "סוג פעילות", "type", "action type"),
    "date": (COL_DATE, "תאריך פעילות", "תאריך פעולה", "date", "activity date"),
}

# Body-cell values that mean "absent" in a TYPE 3 matrix; everything else that
# is non-empty counts as present (mirrors the Excel "any non-empty = present").
_ABSENT_TOKENS = {"", "0", "-", "false", "absent", "no", "לא", ABSENT}


def _norm(text: str) -> str:
    """Collapse a header cell to a comparison key: lowercase, no dots, single spaces."""
    return re.sub(r"\s+", " ", (text or "").strip().lower().replace(".", "")).strip()


_HEADER_MAP = {_norm(name): fieldname
               for fieldname, names in _HEADER_ALIASES.items()
               for name in names}


# ----------------------------------------------------------------------- result
@dataclass
class TabularPaste:
    """Outcome of pasting a TYPE 1 / 2 block."""
    rows: list[dict] = field(default_factory=list)  # grid-shaped row dicts
    skipped: int = 0       # fully-empty lines dropped
    flagged: int = 0       # loaded rows with an invalid/missing required cell
    has_header: bool = False
    warnings: list[str] = field(default_factory=list)
    error: str | None = None  # set → nothing usable parsed

    @property
    def loaded(self) -> int:
        return len(self.rows)

    @property
    def summary(self) -> str:
        if self.error:
            return self.error
        parts = [f"נטענו {self.loaded} שורות"]
        if self.skipped:
            parts.append(f"דולגו {self.skipped} ריקות")
        if self.flagged:
            parts.append(f"{self.flagged} לתיקון")
        parts.extend(self.warnings)
        return " · ".join(parts)


@dataclass
class MatrixPaste:
    """Outcome of pasting a TYPE 3 attendance matrix."""
    start_time: str = ""
    end_time: str = ""
    dates: list[str] = field(default_factory=list)
    participants: list[dict] = field(default_factory=list)  # {"id", "present": [bool]}
    skipped: int = 0
    flagged: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def summary(self) -> str:
        if self.error:
            return self.error
        parts = [f"נטענו {len(self.participants)} משתתפים · {len(self.dates)} תאריכים"]
        if self.skipped:
            parts.append(f"דולגו {self.skipped} ריקות")
        if self.flagged:
            parts.append(f"{self.flagged} לתיקון")
        parts.extend(self.warnings)
        return " · ".join(parts)


# ------------------------------------------------------------------- splitting
def _split(text: str) -> list[list[str]]:
    """Clipboard text → grid of cells. Splits rows on newlines, cells on TAB.

    Trailing blank lines (Excel appends one when copying a block) are dropped so
    they don't inflate the skipped count; interior blanks are kept and handled
    as empty rows by the callers."""
    norm = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = norm.split("\n")
    while lines and lines[-1].strip() == "":
        lines.pop()
    return [line.split("\t") for line in lines]


# --------------------------------------------------------------------- tabular
def parse_tabular(text: str, fields: tuple[str, ...]) -> TabularPaste:
    """Parse a pasted block for a tabular TYPE.

    ``fields`` is the TYPE's column order: ``("id", "type", "date")`` for TYPE 1,
    ``("id",)`` for TYPE 2. Returned rows are keyed by exactly those fields.
    """
    grid = _split(text)
    if not grid:
        return TabularPaste(error="אין מה להדביק — הלוח ריק")

    mapping, has_header, warnings = _detect_tabular_header(grid[0], fields)
    data = grid[1:] if has_header else grid

    res = TabularPaste(has_header=has_header, warnings=warnings)
    for cells in data:
        if not any(c.strip() for c in cells):
            res.skipped += 1
            continue
        row = {f: "" for f in fields}
        for col_idx, fieldname in mapping.items():
            if col_idx < len(cells):
                row[fieldname] = cells[col_idx].strip()
        res.rows.append(row)
        if not _tabular_row_ok(row, fields):
            res.flagged += 1

    if not res.rows:
        res.error = "לא נמצאו שורות נתונים בהדבקה"
    return res


def _detect_tabular_header(cells: list[str], fields: tuple[str, ...]):
    """Return ``(mapping, has_header, warnings)``.

    ``mapping`` is ``{column_index: field}``. A header is recognized when at
    least one cell matches a known column name; otherwise columns map by
    position to ``fields``."""
    matched = {i: _HEADER_MAP[n] for i, c in enumerate(cells)
               for n in (_norm(c),) if n in _HEADER_MAP}

    if matched:
        mapping = {i: f for i, f in matched.items() if f in fields}
        warnings: list[str] = []
        present = set(mapping.values())
        missing = [_FIELD_LABEL[f] for f in fields if f not in present]
        if missing:
            warnings.append("עמודות חסרות: " + ", ".join(missing))
        # Header cells that are non-empty but map to nothing this TYPE wants.
        extra = [cells[i].strip() for i, c in enumerate(cells)
                 if c.strip() and mapping.get(i) is None]
        if extra:
            warnings.append("עמודות שלא נטענו: " + ", ".join(extra))
        return mapping, True, warnings

    # No header → positional mapping onto the TYPE's natural column order.
    mapping = {i: fields[i] for i in range(min(len(cells), len(fields)))}
    warnings = []
    if len(cells) > len(fields):
        warnings.append(f"יש יותר עמודות מהצפוי — {len(cells) - len(fields)} עודפות לא נטענו")
    return mapping, False, warnings


def _tabular_row_ok(row: dict, fields: tuple[str, ...]) -> bool:
    """A row is clean only if every required cell is present and valid — the
    same judgement the grid renders as a red/normal cell."""
    if "id" in fields and not id_valid(row.get("id", "")):
        return False
    if "type" in fields and not type_valid(row.get("type", "")):
        return False
    if "date" in fields and not RE_LOOSE_DATE.match(row.get("date", "").strip()):
        return False
    return True


# ---------------------------------------------------------------------- matrix
def parse_matrix(text: str) -> MatrixPaste:
    """Parse a pasted TYPE 3 attendance matrix.

    Expected layout (identical to the Excel attendance sheet):
      * top-left cell: ``HH:MM|HH:MM`` session times (or blank);
      * rest of the first row: one date per column;
      * first column of each later row: a participant ID;
      * any non-empty body cell: present (``"לא נוכח"`` / ``0`` / blank = absent).
    """
    grid = _split(text)
    if not grid:
        return MatrixPaste(error="אין מה להדביק — הלוח ריק")

    header = grid[0]
    res = MatrixPaste()
    res.start_time, res.end_time = _parse_times(header[0] if header else "")
    if not (res.start_time and res.end_time):
        res.warnings.append("שעות המפגש לא זוהו — הזן אותן ידנית")

    # Date columns: every non-empty cell from the 2nd column on, shown to the
    # user as Israeli d.m.yyyy (a pasted ISO date is converted for display;
    # the ISO form is restored only when the matrix is handed to the processor).
    date_cols: list[tuple[int, str]] = []
    bad_dates: list[str] = []
    for i in range(1, len(header)):
        raw = header[i].strip()
        if not raw:
            continue
        disp = normalize_display_date(raw)
        date_cols.append((i, disp or raw))
        if disp is None:
            bad_dates.append(raw)
    res.dates = [d for _i, d in date_cols]
    if not date_cols:
        res.error = "לא זוהו תאריכים בשורה הראשונה של ההדבקה"
        return res
    if bad_dates:
        res.warnings.append("תאריכים שלא זוהו כתאריך: " + ", ".join(bad_dates))

    for cells in grid[1:]:
        if not any(c.strip() for c in cells):
            res.skipped += 1
            continue
        pid = cells[0].strip() if cells else ""
        if not pid:
            res.skipped += 1
            continue
        present = [_present_cell(cells[col_idx] if col_idx < len(cells) else "")
                   for col_idx, _d in date_cols]
        res.participants.append({"id": pid, "present": present})
        if not id_valid(pid):
            res.flagged += 1

    if not res.participants:
        res.error = "לא נמצאו משתתפים בהדבקה"
    return res


def _parse_times(cell: str) -> tuple[str, str]:
    """Pull ``start, end`` out of a ``HH:MM|HH:MM`` top-left cell, else ``("","")``."""
    s = (cell or "").strip()
    if "|" not in s:
        return "", ""
    a, _, b = s.partition("|")
    a, b = a.strip(), b.strip()
    if RE_TIME.match(a) and RE_TIME.match(b):
        return a, b
    return "", ""


def _present_cell(value: str) -> bool:
    return _norm(value) not in _ABSENT_TOKENS
