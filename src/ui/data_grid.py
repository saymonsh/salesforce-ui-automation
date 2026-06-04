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

from typing import Callable, Optional

import flet as ft
import pyperclip

from src.automation.data_source import MemoryMatrixSource, MemoryTabularSource
# The column keys, attendance tokens, regexes and per-cell validators live in
# paste_parser so the typed path (here) and the smart-paste path (#17) judge a
# cell identically. Aliased to the private names this module already uses.
from src.ui.paste_parser import (
    ABSENT as _ABSENT,
    COL_DATE as _COL_DATE,
    COL_ID as _COL_ID,
    COL_TYPE as _COL_TYPE,
    PRESENT as _PRESENT,
    RE_LOOSE_DATE as _RE_LOOSE_DATE,
    RE_TIME as _RE_TIME,
    digits as _digits,
    id_valid,
    normalize_display_date,
    normalize_iso_date,
    parse_matrix,
    parse_tabular,
    type_valid,
)
from src.ui.theme import Color, Font, Radius, Space, Type

_CELL_BORDER = ft.Colors.with_opacity(0.6, "#ffffff")


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
        self._note_text: Optional[ft.Text] = None  # inline smart-paste feedback line

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
        self._note_text = None

    def build_surface(self) -> ft.Control:
        """Build (or rebuild) the editor surface for the dialog. Returns the root."""
        self._summary_text = ft.Text(
            self.summary(), size=Type.CAPTION[0], color=Color.TEXT_SECONDARY,
            weight=ft.FontWeight.W_600,
        )
        # Inline smart-paste feedback (issue #17). Hidden until a paste happens.
        self._note_text = ft.Text(
            "", size=Type.CAPTION[0], color=Color.TEXT_SECONDARY,
            weight=ft.FontWeight.W_600, visible=False,
            text_align=ft.TextAlign.RIGHT, selectable=True,
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
                self._note_text,
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
            ft.Row(spacing=Space.SM, controls=[add_btn, self._paste_button()]),
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
        # on_change stores the value ONLY — no .update() while the field is
        # focused (that resets the cursor in Flet 0.84). Validation/recolor runs
        # on_blur, when the field is no longer focused. See flet-ui-gotchas.
        field.on_change = lambda e, r=row, k=key: self._store(r, k, e.control.value)
        field.on_blur = lambda e, r=row, k=key, f=field: self._validate_cell(r, k, f)
        self._style_cell(field, self._cell_ok(key, row.get(key, "")))
        return field

    def _store(self, target: dict, key: str, value: str) -> None:
        """Commit a keystroke to the model without touching the view."""
        target[key] = value

    def _validate_cell(self, row: dict, key: str, field: ft.TextField) -> None:
        self._style_cell(field, self._cell_ok(key, row.get(key, "")))
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
            self._paste_button(),
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
        field.on_change = lambda e, w=which: self._store_time(w, e.control.value)
        field.on_blur = lambda e, w=which, f=field: self._validate_time(w, f)
        self._style_cell(field, not value.strip() or bool(_RE_TIME.match(value.strip())))
        return field

    def _store_time(self, which: str, value: str) -> None:
        if which == "start":
            self._t3_start = value
        else:
            self._t3_end = value

    def _validate_time(self, which: str, field: ft.TextField) -> None:
        val = self._t3_start if which == "start" else self._t3_end
        ok = not val.strip() or bool(_RE_TIME.match(val.strip()))
        self._style_cell(field, ok)
        field.update()
        self._refresh_summary()
        self._emit_change()

    def _date_header_field(self, value: str, idx: int, width: int) -> ft.TextField:
        # Shown to the user in Israeli dd.mm.yyyy; converted to ISO only when the
        # matrix is built (see _build_matrix). Typed ISO is still accepted.
        field = ft.TextField(
            value=value, width=width, hint_text="dd.mm.yyyy", text_size=Type.CAPTION[0],
            dense=True, content_padding=Space.XS, border_radius=Radius.SM,
            border_color=_CELL_BORDER, focused_border_color=Color.BRAND, cursor_color=Color.BRAND,
            bgcolor=ft.Colors.with_opacity(0.5, "#ffffff"), color=Color.TEXT_PRIMARY,
        )
        field.on_change = lambda e, i=idx: self._store_date(i, e.control.value)
        field.on_blur = lambda e, i=idx, f=field: self._validate_date(i, f)
        self._style_cell(field, not value.strip() or normalize_iso_date(value) is not None)
        return field

    def _store_date(self, idx: int, value: str) -> None:
        if 0 <= idx < len(self._t3_dates):
            self._t3_dates[idx] = value

    def _validate_date(self, idx: int, field: ft.TextField) -> None:
        val = self._t3_dates[idx] if 0 <= idx < len(self._t3_dates) else ""
        ok = not val.strip() or normalize_iso_date(val) is not None
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
        field.on_change = lambda e, p=part: self._store(p, "id", e.control.value)
        field.on_blur = lambda e, p=part, f=field: self._validate_t3_id(p, f)
        s = part.get("id", "").strip()
        self._style_cell(field, not s or id_valid(s))
        return field

    def _validate_t3_id(self, part: dict, field: ft.TextField) -> None:
        s = part.get("id", "").strip()
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

    # --- smart paste (issue #17) -------------------------------------------
    def _paste_button(self) -> ft.Control:
        tip = ("הדבק טווח תאים שהועתק מ-Excel / Google Sheets. "
               "כותרות מזוהות אוטומטית; שורות פגומות מסומנות באדום.")
        return ft.TextButton(
            "הדבק מ-Excel", icon=ft.Icons.CONTENT_PASTE_ROUNDED, tooltip=tip,
            style=ft.ButtonStyle(color=Color.BRAND),
            on_click=lambda _e: self._paste_clicked(),
        )

    def _paste_clicked(self) -> None:
        try:
            text = pyperclip.paste()
        except Exception as ex:  # pragma: no cover - platform clipboard failure
            self._set_note(f"קריאת הלוח נכשלה: {ex}", level="error")
            return
        if not (text and text.strip()):
            self._set_note("אין מה להדביק — הלוח ריק", level="error")
            return
        if self._type == "3":
            self._apply_matrix_paste(text)
        elif self._type == "2":
            self._apply_tabular_paste(text, ("id",), self._t2_rows, self._new_t2_row)
        else:
            self._apply_tabular_paste(text, ("id", "type", "date"),
                                      self._t1_rows, self._new_t1_row)

    def _apply_tabular_paste(self, text: str, fields, rows: list, factory) -> None:
        res = parse_tabular(text, fields)
        if not res.rows:
            self._set_note(res.summary, level="error")
            return
        # Keep already-typed rows, drop the blank seed rows, append the paste.
        kept = [r for r in rows if any((r.get(k) or "").strip() for k in fields)]
        pasted = [{k: r.get(k, "") for k in fields} for r in res.rows]
        combined = kept + pasted
        rows[:] = combined if combined else [factory()]
        self._render_body()
        self._body.update()
        self._refresh_summary()
        self._emit_change()
        self._set_note(res.summary, level=self._paste_level(res))

    def _apply_matrix_paste(self, text: str) -> None:
        res = parse_matrix(text)
        if res.error:
            self._set_note(res.error, level="error")
            return
        self._t3_start = res.start_time
        self._t3_end = res.end_time
        self._t3_dates = list(res.dates) or [""]
        self._t3_parts = [{"id": p["id"], "present": list(p["present"])}
                          for p in res.participants] or [self._new_t3_part()]
        self._rerender_t3()
        self._set_note(res.summary, level=self._paste_level(res))

    @staticmethod
    def _paste_level(res) -> str:
        return "warn" if (res.flagged or res.warnings) else "ok"

    def _set_note(self, message: str, level: str = "ok") -> None:
        if self._note_text is None:
            return
        self._note_text.value = message
        self._note_text.color = {
            "ok": Color.SUCCESS, "warn": Color.WARNING, "error": Color.DANGER,
        }.get(level, Color.TEXT_SECONDARY)
        self._note_text.visible = bool(message)
        self._note_text.update()

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
            if s and normalize_iso_date(s) is None:
                reasons.append(f"תאריך בעמודה {i} חייב להיות תאריך תקין (dd.mm.yyyy)")
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

    # ----------------------------------------------------------- draft persistence
    def export_state(self) -> dict:
        """Snapshot every per-TYPE model to a JSON-serializable dict (issue #18).

        All three models are saved together (not just the active TYPE), so the
        draft restores whatever the user was editing regardless of which TYPE is
        selected on the next launch. The values are already plain str/bool/list.
        """
        return {
            "t1": self._t1_rows,
            "t2": self._t2_rows,
            "t3": {
                "start": self._t3_start,
                "end": self._t3_end,
                "dates": self._t3_dates,
                "parts": self._t3_parts,
            },
        }

    def restore_state(self, state: dict) -> None:
        """Load a draft saved by :meth:`export_state` back into the models.

        Defensive by design — the draft is a hand-editable on-disk file, so every
        field is coerced and TYPE 3's per-date ``present`` lists are re-aligned to
        the restored date count. Does not touch the live controls (called before
        the editor is ever built); the active TYPE is set separately from config.
        """
        if not isinstance(state, dict):
            return

        t1 = state.get("t1")
        if isinstance(t1, list):
            rows = [
                {"id": str(r.get("id", "")), "type": str(r.get("type", "")), "date": str(r.get("date", ""))}
                for r in t1 if isinstance(r, dict)
            ]
            self._t1_rows = rows or [self._new_t1_row()]

        t2 = state.get("t2")
        if isinstance(t2, list):
            rows = [{"id": str(r.get("id", ""))} for r in t2 if isinstance(r, dict)]
            self._t2_rows = rows or [self._new_t2_row()]

        t3 = state.get("t3")
        if isinstance(t3, dict):
            dates = [str(d) for d in t3.get("dates", []) if d is not None]
            self._t3_dates = dates or [""]
            self._t3_start = str(t3.get("start", ""))
            self._t3_end = str(t3.get("end", ""))
            width = len(self._t3_dates)
            parts = []
            for p in t3.get("parts", []):
                if not isinstance(p, dict):
                    continue
                present = [bool(x) for x in p.get("present", [])]
                present = (present + [False] * width)[:width]  # re-align to dates
                parts.append({"id": str(p.get("id", "")), "present": present})
            self._t3_parts = parts or [self._new_t3_part()]

    # ------------------------------------------------------------- excel import
    def note(self, message: str, level: str = "ok") -> None:
        """Public hook for the host to surface an import/export result on the
        grid's inline feedback line (reuses the smart-paste note)."""
        self._set_note(message, level)

    def import_tabular_rows(self, incoming: list[dict]) -> str:
        """Load grid-keyed rows read from Excel (TYPE 1 / 2) into the table.

        Unlike smart-paste (which *appends* a copied selection,
        :meth:`_apply_tabular_paste`), importing a file *replaces* the current
        rows: the user is loading "this file", not adding to whatever the draft
        already held from a previous session — appending there would silently mix
        old and new batches. (Now that Excel is the only file path, this is the
        intuitive behaviour.)
        """
        if self._type == "2":
            fields, factory = ("id",), self._new_t2_row
        else:  # TYPE 1
            fields, factory = ("id", "type", "date"), self._new_t1_row
        incoming = [r for r in incoming if any((r.get(k) or "").strip() for k in fields)]
        if not incoming:
            msg = "לא נמצאו שורות לייבוא בקובץ"
            self._set_note(msg, "error")
            return msg
        rows = [{k: r.get(k, "") for k in fields} for r in incoming]
        if self._type == "2":
            self._t2_rows = rows or [factory()]
        else:
            self._t1_rows = rows or [factory()]
        if self._body is not None:
            self._render_body()
            self._body.update()
        self._refresh_summary()
        self._emit_change()
        msg = f"יובאו {len(incoming)} שורות מ-Excel (החליפו את הטבלה)"
        self._set_note(msg, "ok")
        return msg

    def import_matrix(self, matrix: dict) -> str:
        """Load a TYPE 3 attendance matrix read from Excel into the grid.

        The matrix dict carries ISO ``yyyy-mm-dd`` dates and ``נוכח``/``לא נוכח``
        tokens; convert them back to the grid's editable form (display dates +
        per-date booleans). Replaces the current matrix (a matrix is one whole).
        """
        iso_dates = [str(d) for d in matrix.get("dates", [])]
        self._t3_start = str(matrix.get("start_time", ""))
        self._t3_end = str(matrix.get("end_time", ""))
        self._t3_dates = [normalize_display_date(d) or d for d in iso_dates] or [""]
        parts = []
        for p in matrix.get("participants", []):
            attendance = p.get("attendance", {})
            present = [attendance.get(d) == _PRESENT for d in iso_dates]
            parts.append({"id": str(p.get("id_number", "")), "present": present})
        self._t3_parts = parts or [self._new_t3_part()]
        self._rerender_t3()
        msg = f"יובאו {len(parts)} משתתפים · {len(iso_dates)} תאריכים"
        self._set_note(msg, "ok")
        return msg

    def _build_matrix(self) -> dict:
        # The grid holds Israeli dd.mm.yyyy dates; the processor wants ISO
        # (strptime "%Y-%m-%d %H:%M"), so convert here at the source boundary.
        date_cols = [(col_index, normalize_iso_date(raw) or raw)
                     for col_index, raw in self._t3_filled_dates()]
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
