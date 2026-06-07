"""Read an existing Excel file *into* the manual-entry grid (issue #18, epic #14
step 4).

This is the inverse direction of :meth:`DataGridView.to_source`: instead of the
grid producing a data source, an Excel file is loaded into the grid's editable
string-cell shape so the user can keep editing it. Excel thus becomes an *import
path* rather than a separate, opaque input medium — the old Excel workflow is
preserved, just routed through the grid.

The two reader functions mirror the two processor families (see ``data_source``):

  * :func:`read_tabular` — TYPE 1 / TYPE 2: returns grid-keyed row dicts
    (``id`` / ``type`` / ``date``) with every cell already stringified into the
    shapes the grid validates (digits-only IDs, ``d/m/Y`` dates).
  * :func:`read_matrix` — TYPE 3: delegates to
    :func:`ExcelParser.parse_attendance_matrix`, whose dict the grid converts back
    to its editable form in :meth:`DataGridView.import_matrix`.
"""
import pandas as pd

from src.automation.excel_parser import ExcelParser

# The Hebrew column headers the processors read (kept here as literals so this
# automation-layer module doesn't import the UI's paste_parser).
_COL_ID = "תעודות זהות"
_COL_TYPE = "סוג"
_COL_DATE = "תאריך"


def _str_id(value) -> str:
    """Stringify an ID cell without pandas' float/scientific artefacts.

    Excel commonly types an ID column as numbers, so ``123456789`` arrives as
    ``123456789.0``; collapse that back to plain digits. The grid pads/validates
    afterwards exactly as the Excel path did.
    """
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


def _str_type(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


def _str_date(value) -> str:
    """Render a date cell as Israeli ``d.m.yyyy`` (no leading zeros) — the form the
    tabular grid shows and the Salesforce date field accepts (matching the
    manual-entry path). Built manually, not via ``strftime``, since the no-pad
    directive ``%-d`` isn't portable to Windows.
    """
    if pd.isna(value):
        return ""
    if hasattr(value, "strftime"):  # Timestamp / datetime
        return f"{value.day}.{value.month}.{value.year}"
    s = str(value).strip()
    if not s:
        return ""
    try:
        d = pd.to_datetime(s, dayfirst=True)
        return f"{d.day}.{d.month}.{d.year}"
    except Exception:
        return s  # leave it for the grid to flag as invalid rather than guess


def read_tabular(path: str, type_value) -> list[dict]:
    """Return grid-keyed rows for TYPE 1 / TYPE 2 loaded from ``path``.

    Columns are matched by the Hebrew header names; if a header is missing we
    fall back to position (col 0 = ID, 1 = type, 2 = date) so a header-less or
    renamed sheet still imports something sensible. Fully-empty rows are dropped.
    """
    df = pd.read_excel(path)
    by_name = {str(c).strip(): c for c in df.columns}
    cols = list(df.columns)

    def _col(name, pos):
        if name in by_name:
            return by_name[name]
        return cols[pos] if pos < len(cols) else None

    id_col = _col(_COL_ID, 0)
    type_col = _col(_COL_TYPE, 1)
    date_col = _col(_COL_DATE, 2)

    is_t1 = str(type_value) == "1"
    rows: list[dict] = []
    for _, r in df.iterrows():
        rid = _str_id(r[id_col]) if id_col is not None else ""
        if is_t1:
            row = {
                "id": rid,
                "type": _str_type(r[type_col]) if type_col is not None else "",
                "date": _str_date(r[date_col]) if date_col is not None else "",
            }
            keys = ("id", "type", "date")
        else:
            row = {"id": rid}
            keys = ("id",)
        if any((row.get(k) or "").strip() for k in keys):
            rows.append(row)
    return rows


def read_matrix(path: str) -> dict:
    """Return the TYPE 3 attendance matrix dict for ``path`` (same shape the
    Excel and manual-entry paths both produce)."""
    return ExcelParser.parse_attendance_matrix(path)
