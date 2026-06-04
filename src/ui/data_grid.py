"""In-app manual-entry grid (issue #16, epic #14 step 2).

An editable table whose columns are derived from ``config.TYPE``. It is the
manual-entry counterpart to loading an Excel file: the user types/edits rows
here, and :meth:`DataGridView.to_source` hands the worker the *same* unified data
model the Excel path produces (issue #15) — a :class:`MemoryTabularSource`
(TYPE 1/2) or :class:`MemoryMatrixSource` (TYPE 3). The processors can't tell the
two input media apart.

Design notes:
  * The backing model is plain Python data (lists of dicts of strings + bools),
    so it survives the grid dialog being closed and reopened — the view controls
    are rebuilt from the model each time the surface is built.
  * Cells are ``TextField`` / ``Checkbox`` only — no ``Dropdown`` (Flet 0.84 has
    no dropdown blur, see the project memory). ``update()`` is only ever called
    from event handlers (post-mount), never during build.
  * Validation is lenient by design and mirrors the Excel path: IDs are
    digits-only ≤ 9 (no Israeli check-digit), TYPE 3 IDs are padded to 9 exactly
    like ``ExcelParser.parse_attendance_matrix``, and TYPE 3 dates/times use the
    ``YYYY-MM-DD`` / ``HH:MM`` shapes ``AttendanceProcessor`` feeds to strptime.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

import flet as ft

from src.automation.data_source import MemoryMatrixSource, MemoryTabularSource
from src.ui.theme import Color, Font, Radius, Space, Type

# Hebrew column keys the processors read — must match the Excel column headers.
_COL_ID = "תעודות זהות"
_COL_TYPE = "סוג"
_COL_DATE = "תאריך"

# Attendance cell statuses, identical to ExcelParser.parse_attendance_matrix.
_PRESENT = "נוכח"
_ABSENT = "לא נוכח"

# TYPE 3 needs YYYY-MM-DD (AttendanceProcessor parses "%Y-%m-%d %H:%M").
_RE_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# TYPE 1 date is sent verbatim into the Salesforce field — accept the common
# Israeli D/M/Y (any of / . -) or an ISO date; kept lenient on purpose.
_RE_LOOSE_DATE = re.compile(r"^(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{4}-\d{2}-\d{2})$")
_RE_TIME = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")

_CELL_BORDER = ft.Colors.with_opacity(0.6, "#ffffff")


def _digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def id_valid(value: str) -> bool:
    """Digits-only, 1–9 chars — matches today's Excel behavior (no check-digit)."""
    s = (value or "").strip()
    return s.isdigit() and 1 <= len(s) <= 9


def type_valid(value: str) -> bool:
    s = (value or "").strip()
    return s.isdigit() and 1 <= int(s) <= 6


class DataGridView:
    """Holds the manual-entry model for the current TYPE and builds its editor.

    One instance lives on :class:`MainView`; the TYPE selector calls
    :meth:`rebuild_for_type`. Each TYPE keeps its own independent model, so
    switching back and forth never loses typed data.
    """

    def __init__(self, page: ft.Page, on_change: Optional[Callable[[], None]] = None):
        self.page = page
        self._on_change = on_change
        self._type = "1"

        # Independent per-TYPE models, each seeded with one empty row.
        self._t1_rows: list[dict] = [self._new_t1_row()]
        self._t2_rows: list[dict] = [self._new_t2_row()]
        self._t3_start = ""
        self._t3_end = ""
        self._t3_dates: list[str] = [""]
        self._t3_parts: list[dict] = [self._new_t3_part()]

        # Built lazily when the dialog opens.
        self._body: Optional[ft.Container] = None
        self._summary_text: Optional[ft.Text] = None

    # ----------------------------------------------------------------- model rows
    @staticmethod
    def _new_t1_row() -> dict:
        return {"id": "", "type": "", "date": ""}

    @staticmethod
    def _new_t2_row() -> dict:
        return {"id": ""}

    def _new_t3_part(self) -> dict:
        return {"id": "", "present": [False for _ in self._t3_dates]}

    # --------------------------------------------------------------------- public
    def rebuild_for_type(self, type_value) -> None:
        """Point the grid at a different TYPE and re-render if a surface is open."""
        self._type = str(type_value) if type_value is not None else "1"
        if self._body is not None:
            self._render_body()
            self._body.update()
        self._emit_change()

    def detach(self) -> None:
        """Drop references to the live controls when the dialog closes, so a later
        :meth:`rebuild_for_type` (triggered while the editor isn't mounted) won't
        try to ``update()`` an unmounted control. The data model is untouched."""
        self._body = None
        self._summary_text = None

    def build_surface(self) -> ft.Control:
        """Build (or rebuild) the editor surface for the dialog. Returns the root."""
        self._summary_text = ft.Text(
            self.summary(), size=Type.CAPTION[0], color=Color.TEXT_SECONDARY,
            weight=ft.FontWeight.W_600,
        )
        self._body = ft.Container(expand=True)
        self._render_body()

        title = ft.Row(
            spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.TABLE_CHART_ROUNDED, size=18, color=Color.BRAND),
                ft.Text("טבלת הזנה ידנית", size=Type.TITLE[0], weight=ft.FontWeight.W_700,
                        color=Color.TEXT_PRIMARY),
            ],
        )
        header = ft.Container(
            padding=ft.padding.only(bottom=Space.SM),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[title, self._summary_text],
            ),
        )
        return ft.Container(
            expand=True, padding=Space.LG,
            content=ft.Column(spacing=Space.SM, expand=True, controls=[
                header,
                ft.Divider(color=ft.Colors.with_opacity(0.5, Color.BORDER), height=1),
                self._body,
            ]),
        )

    # ------------------------------------------------------------------ rendering
    def _render_body(self) -> None:
        if self._type == "3":
            self._body.content = self._render_t3()
        elif self._type == "2":
            self._body.content = self._render_tabular(("id",), (_COL_ID,), self._t2_rows,
                                                      self._new_t2_row)
        else:  # default TYPE 1
            self._body.content = self._render_t1()

    # --- TYPE 1 / TYPE 2 (tabular) -----------------------------------------
    def _render_t1(self) -> ft.Control:
        context = ft.Container(
            padding=ft.padding.only(bottom=Space.XS),
            content=ft.Text(
                "מספר ותיאור הפעילות נלקחים מההגדרות ומשותפים לכל השורות.",
                size=Type.CAPTION[0], color=Color.TEXT_TERTIARY, italic=True,
            ),
        )
        grid = self._render_tabular(
            ("id", "type", "date"),
            (_COL_ID, _COL_TYPE, _COL_DATE),
            self._t1_rows, self._new_t1_row,
        )
        return ft.Column(spacing=Space.XS, expand=True, controls=[context, grid])

    def _render_tabular(self, keys, labels, rows, factory) -> ft.Control:
        widths = {"id": 180, "type": 110, "date": 180}

        # Column header strip.
        head_cells: list[ft.Control] = [
            ft.Container(width=widths[k], content=ft.Text(
                lbl, size=Type.CAPTION[0], weight=ft.FontWeight.W_700, color=Color.TEXT_SECONDARY))
            for k, lbl in zip(keys, labels)
        ]
        head_cells.append(ft.Container(width=44))  # delete-button column
        header = ft.Row(spacing=Space.SM, controls=head_cells)

        body_rows: list[ft.Control] = []
        for i, row in enumerate(rows):
            cells: list[ft.Control] = []
            for k in keys:
                cells.append(self._tabular_cell(row, k, widths[k]))
            cells.append(self._delete_button(
                lambda _e, r=row: self._del_tabular_row(rows, r, factory)))
            body_rows.append(ft.Row(spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.START,
                                    controls=cells))

        rows_list = ft.ListView(expand=True, spacing=Space.XS, controls=body_rows)
        add_btn = ft.TextButton(
            "הוסף שורה", icon=ft.Icons.ADD_ROUNDED,
            style=ft.ButtonStyle(color=Color.BRAND),
            on_click=lambda _e: self._add_tabular_row(rows, factory),
        )
        return ft.Column(spacing=Space.SM, expand=True, controls=[
            header,
            ft.Container(expand=True, content=rows_list),
            ft.Row(controls=[add_btn]),
        ])

    def _tabular_cell(self, row: dict, key: str, width: int) -> ft.TextField:
        hint = {"id": "מספר זהות", "type": "1–6", "date": "dd/mm/yyyy"}[key]
        field = ft.TextField(
            value=row.get(key, ""), width=width, hint_text=hint,
            text_size=Type.BODY[0], dense=True, content_padding=Space.SM,
            border_radius=Radius.SM, border_color=_CELL_BORDER,
            focused_border_color=Color.BRAND, cursor_color=Color.BRAND,
            bgcolor=ft.Colors.with_opacity(0.5, "#ffffff"), color=Color.TEXT_PRIMARY,
        )
        field.on_change = lambda e, r=row, k=key, f=field: self._on_cell_edit(e, r, k, f)
        self._style_cell(field, self._cell_ok(key, row.get(key, "")))
        return field

    def _on_cell_edit(self, e, row: dict, key: str, field: ft.TextField) -> None:
        row[key] = e.control.value
        self._style_cell(field, self._cell_ok(key, row[key]))
        field.update()
        self._refresh_summary()
        self._emit_change()

    def _cell_ok(self, key: str, value: str) -> bool:
        """Per-cell validity. Empty is tolerated only on the all-empty trailing
        row; a partially-filled row flags its own missing/invalid cells."""
        s = (value or "").strip()
        if not s:
            return True  # emptiness is judged at row level, not per cell
        if key == "id":
            return id_valid(s)
        if key == "type":
            return type_valid(s)
        if key == "date":
            return bool(_RE_LOOSE_DATE.match(s))
        return True

    def _add_tabular_row(self, rows: list, factory) -> None:
        rows.append(factory())
        self._render_body()
        self._body.update()
        self._refresh_summary()
        self._emit_change()

    def _del_tabular_row(self, rows: list, row: dict, factory) -> None:
        if row in rows:
            rows.remove(row)
        if not rows:
            rows.append(factory())  # always keep one editable row
        self._render_body()
        self._body.update()
        self._refresh_summary()
        self._emit_change()

    # --- TYPE 3 (attendance matrix) ----------------------------------------
    def _render_t3(self) -> ft.Control:
        # Session start/end time.
        self._t3_start_field = self._time_field(self._t3_start, "start")
        self._t3_end_field = self._time_field(self._t3_end, "end")
        times = ft.Row(spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
            ft.Text("שעות מפגש:", size=Type.CAPTION[0], color=Color.TEXT_SECONDARY,
                    weight=ft.FontWeight.W_600),
            self._t3_start_field,
            ft.Text("עד", size=Type.CAPTION[0], color=Color.TEXT_TERTIARY),
            self._t3_end_field,
        ])

        col_w = 130
        id_w = 150
        # Header: ID label + a date field per column (+ delete date) + add-date.
        head: list[ft.Control] = [ft.Container(width=id_w, content=ft.Text(
            _COL_ID, size=Type.CAPTION[0], weight=ft.FontWeight.W_700, color=Color.TEXT_SECONDARY))]
        for di, date_val in enumerate(self._t3_dates):
            head.append(ft.Container(width=col_w, content=ft.Column(spacing=2, controls=[
                self._date_header_field(date_val, di, col_w),
                ft.Container(
                    alignment=ft.Alignment.CENTER,
                    content=ft.IconButton(
                        ft.Icons.CLOSE_ROUNDED, icon_size=14, icon_color=Color.TEXT_TERTIARY,
                        tooltip="מחק תאריך", on_click=lambda _e, i=di: self._del_date(i)),
                ),
            ])))
        head.append(ft.Container(width=44))  # delete-participant column
        header_row = ft.Row(spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.START, controls=head)

        # Participant rows: ID + a present/absent checkbox per date.
        part_rows: list[ft.Control] = []
        for p in self._t3_parts:
            cells: list[ft.Control] = [self._t3_id_cell(p, id_w)]
            for di in range(len(self._t3_dates)):
                cells.append(ft.Container(
                    width=col_w, alignment=ft.Alignment.CENTER,
                    content=ft.Checkbox(
                        value=p["present"][di], active_color=Color.BRAND,
                        on_change=lambda e, part=p, idx=di: self._on_attend_toggle(e, part, idx)),
                ))
            cells.append(self._delete_button(lambda _e, part=p: self._del_part(part)))
            part_rows.append(ft.Row(spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    controls=cells))

        matrix = ft.Column(spacing=Space.XS, controls=[header_row, *part_rows], tight=True)
        # Horizontal scroll so many dates don't overflow the dialog width.
        scroller = ft.Row(scroll=ft.ScrollMode.AUTO, controls=[matrix])
        scroll_area = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, controls=[scroller])

        toolbar = ft.Row(spacing=Space.SM, controls=[
            ft.TextButton("הוסף משתתף", icon=ft.Icons.PERSON_ADD_ROUNDED,
                          style=ft.ButtonStyle(color=Color.BRAND),
                          on_click=lambda _e: self._add_part()),
            ft.TextButton("הוסף תאריך", icon=ft.Icons.EVENT_ROUNDED,
                          style=ft.ButtonStyle(color=Color.BRAND),
                          on_click=lambda _e: self._add_date()),
        ])
        return ft.Column(spacing=Space.SM, expand=True, controls=[
            times,
            ft.Divider(color=ft.Colors.with_opacity(0.4, Color.BORDER), height=1),
            ft.Container(expand=True, content=scroll_area),
            toolbar,
        ])

    def _time_field(self, value: str, which: str) -> ft.TextField:
        field = ft.TextField(
            value=value, width=92, hint_text="HH:MM", text_align=ft.TextAlign.CENTER,
            text_size=Type.BODY[0], dense=True, content_padding=Space.SM,
            border_radius=Radius.SM, border_color=_CELL_BORDER,
            focused_border_color=Color.BRAND, cursor_color=Color.BRAND,
            bgcolor=ft.Colors.with_opacity(0.5, "#ffffff"), color=Color.TEXT_PRIMARY,
        )
        field.on_change = lambda e, w=which, f=field: self._on_time_edit(e, w, f)
        self._style_cell(field, not value.strip() or bool(_RE_TIME.match(value.strip())))
        return field

    def _on_time_edit(self, e, which: str, field: ft.TextField) -> None:
        val = e.control.value
        if which == "start":
            self._t3_start = val
        else:
            self._t3_end = val
        ok = not val.strip() or bool(_RE_TIME.match(val.strip()))
        self._style_cell(field, ok)
        field.update()
        self._refresh_summary()
        self._emit_change()

    def _date_header_field(self, value: str, idx: int, width: int) -> ft.TextField:
        field = ft.TextField(
            value=value, width=width, hint_text="yyyy-mm-dd", text_size=Type.CAPTION[0],
            dense=True, content_padding=Space.XS, border_radius=Radius.SM,
            border_color=_CELL_BORDER, focused_border_color=Color.BRAND, cursor_color=Color.BRAND,
            bgcolor=ft.Colors.with_opacity(0.5, "#ffffff"), color=Color.TEXT_PRIMARY,
        )
        field.on_change = lambda e, i=idx, f=field: self._on_date_edit(e, i, f)
        self._style_cell(field, not value.strip() or bool(_RE_ISO_DATE.match(value.strip())))
        return field

    def _on_date_edit(self, e, idx: int, field: ft.TextField) -> None:
        val = e.control.value
        self._t3_dates[idx] = val
        ok = not val.strip() or bool(_RE_ISO_DATE.match(val.strip()))
        self._style_cell(field, ok)
        field.update()
        self._refresh_summary()
        self._emit_change()

    def _t3_id_cell(self, part: dict, width: int) -> ft.TextField:
        field = ft.TextField(
            value=part.get("id", ""), width=width, hint_text="מספר זהות",
            text_size=Type.BODY[0], dense=True, content_padding=Space.SM,
            border_radius=Radius.SM, border_color=_CELL_BORDER,
            focused_border_color=Color.BRAND, cursor_color=Color.BRAND,
            bgcolor=ft.Colors.with_opacity(0.5, "#ffffff"), color=Color.TEXT_PRIMARY,
        )
        field.on_change = lambda e, p=part, f=field: self._on_t3_id_edit(e, p, f)
        s = part.get("id", "").strip()
        self._style_cell(field, not s or id_valid(s))
        return field

    def _on_t3_id_edit(self, e, part: dict, field: ft.TextField) -> None:
        part["id"] = e.control.value
        s = part["id"].strip()
        self._style_cell(field, not s or id_valid(s))
        field.update()
        self._refresh_summary()
        self._emit_change()

    def _on_attend_toggle(self, e, part: dict, idx: int) -> None:
        part["present"][idx] = bool(e.control.value)
        self._emit_change()

    def _add_part(self) -> None:
        self._t3_parts.append(self._new_t3_part())
        self._rerender_t3()

    def _del_part(self, part: dict) -> None:
        if part in self._t3_parts:
            self._t3_parts.remove(part)
        if not self._t3_parts:
            self._t3_parts.append(self._new_t3_part())
        self._rerender_t3()

    def _add_date(self) -> None:
        self._t3_dates.append("")
        for p in self._t3_parts:
            p["present"].append(False)
        self._rerender_t3()

    def _del_date(self, idx: int) -> None:
        if 0 <= idx < len(self._t3_dates):
            self._t3_dates.pop(idx)
            for p in self._t3_parts:
                if idx < len(p["present"]):
                    p["present"].pop(idx)
        if not self._t3_dates:
            self._t3_dates.append("")
            for p in self._t3_parts:
                p["present"].append(False)
        self._rerender_t3()

    def _rerender_t3(self) -> None:
        self._render_body()
        self._body.update()
        self._refresh_summary()
        self._emit_change()

    # ----------------------------------------------------------------- shared bits
    def _delete_button(self, handler) -> ft.Control:
        return ft.Container(width=44, alignment=ft.Alignment.CENTER, content=ft.IconButton(
            ft.Icons.DELETE_OUTLINE_ROUNDED, icon_size=18, icon_color=Color.DANGER,
            tooltip="מחק שורה", on_click=handler))

    def _style_cell(self, field: ft.TextField, ok: bool) -> None:
        field.border_color = _CELL_BORDER if ok else Color.DANGER
        field.tooltip = None if ok else "ערך לא תקין"

    def _refresh_summary(self) -> None:
        if self._summary_text is not None:
            self._summary_text.value = self.summary()
            self._summary_text.update()

    def _emit_change(self) -> None:
        if self._on_change:
            try:
                self._on_change()
            except Exception:
                pass

    # ------------------------------------------------------------------- queries
    def _t1_filled(self) -> list[dict]:
        return [r for r in self._t1_rows if any((r.get(k) or "").strip() for k in ("id", "type", "date"))]

    def _t2_filled(self) -> list[dict]:
        return [r for r in self._t2_rows if (r.get("id") or "").strip()]

    def _t3_filled_parts(self) -> list[dict]:
        return [p for p in self._t3_parts if (p.get("id") or "").strip()]

    def _t3_filled_dates(self) -> list[tuple[int, str]]:
        return [(i, d.strip()) for i, d in enumerate(self._t3_dates) if d.strip()]

    def is_empty(self) -> bool:
        if self._type == "3":
            return not self._t3_filled_parts() or not self._t3_filled_dates()
        if self._type == "2":
            return not self._t2_filled()
        return not self._t1_filled()

    def invalid_reasons(self) -> list[str]:
        """Human-facing reasons the current data can't run (empty list = valid)."""
        reasons: list[str] = []
        if self._type == "3":
            return self._t3_invalid_reasons()
        if self._type == "2":
            rows = self._t2_filled()
            for n, r in enumerate(rows, 1):
                if not id_valid(r["id"].strip()):
                    reasons.append(f"שורה {n}: ת.ז. לא תקינה")
            return reasons
        # TYPE 1
        for n, r in enumerate(self._t1_filled(), 1):
            rid, rtype, rdate = r["id"].strip(), r["type"].strip(), r["date"].strip()
            if not id_valid(rid):
                reasons.append(f"שורה {n}: ת.ז. לא תקינה")
            if not type_valid(rtype):
                reasons.append(f"שורה {n}: סוג חייב להיות מספר בין 1 ל-6")
            if not rdate or not _RE_LOOSE_DATE.match(rdate):
                reasons.append(f"שורה {n}: תאריך לא תקין")
        return reasons

    def _t3_invalid_reasons(self) -> list[str]:
        reasons: list[str] = []
        if not _RE_TIME.match(self._t3_start.strip()):
            reasons.append("שעת התחלה חייבת להיות בפורמט HH:MM")
        if not _RE_TIME.match(self._t3_end.strip()):
            reasons.append("שעת סיום חייבת להיות בפורמט HH:MM")
        for i, d in enumerate(self._t3_dates, 1):
            s = d.strip()
            if s and not _RE_ISO_DATE.match(s):
                reasons.append(f"תאריך בעמודה {i} חייב להיות בפורמט yyyy-mm-dd")
        if not self._t3_filled_dates():
            reasons.append("נדרש לפחות תאריך אחד")
        for n, p in enumerate(self._t3_filled_parts(), 1):
            if not id_valid(p["id"].strip()):
                reasons.append(f"משתתף {n}: ת.ז. לא תקינה")
        if not self._t3_filled_parts():
            reasons.append("נדרש לפחות משתתף אחד")
        return reasons

    def is_valid(self) -> bool:
        return not self.is_empty() and not self.invalid_reasons()

    def summary(self) -> str:
        if self.is_empty():
            return "אין נתונים"
        if self.invalid_reasons():
            return "יש שורות פגומות"
        if self._type == "3":
            return f"{len(self._t3_filled_parts())} משתתפים · {len(self._t3_filled_dates())} תאריכים"
        n = len(self._t2_filled()) if self._type == "2" else len(self._t1_filled())
        return f"{n} שורות הוקלדו"

    # -------------------------------------------------------------------- export
    def to_source(self):
        """Return a Memory*Source mirroring the Excel shapes, or None if invalid."""
        if not self.is_valid():
            return None
        if self._type == "3":
            return MemoryMatrixSource(self._build_matrix())
        if self._type == "2":
            rows = [{_COL_ID: r["id"].strip()} for r in self._t2_filled()]
            return MemoryTabularSource(rows)
        # TYPE 1 — סוג must be an int (LoginProcessor compares row['סוג'] == 1).
        rows = []
        for r in self._t1_filled():
            rows.append({
                _COL_ID: r["id"].strip(),
                _COL_TYPE: int(r["type"].strip()),
                _COL_DATE: r["date"].strip(),
            })
        return MemoryTabularSource(rows)

    def _build_matrix(self) -> dict:
        date_cols = self._t3_filled_dates()  # [(col_index, date_str)]
        dates = [d for _i, d in date_cols]
        participants = []
        for p in self._t3_filled_parts():
            id_str = _digits(p["id"])
            if len(id_str) <= 9:  # mirror ExcelParser padding to 9
                id_str = id_str.zfill(9)
            attendance = {}
            for col_index, date_str in date_cols:
                present = col_index < len(p["present"]) and p["present"][col_index]
                attendance[date_str] = _PRESENT if present else _ABSENT
            participants.append({"id_number": id_str, "attendance": attendance})
        return {
            "start_time": self._t3_start.strip(),
            "end_time": self._t3_end.strip(),
            "dates": dates,
            "participants": participants,
        }
