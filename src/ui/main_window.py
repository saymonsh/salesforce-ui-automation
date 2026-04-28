import os
import threading
from typing import Callable, Optional

import flet as ft

from src.ui.help_dialog import create_help_dialog


class MainView:
    def __init__(self, page: ft.Page):
        self.page = page
        self._lock = threading.RLock()
        self._build_page()
        self._build_controls()
        self._render()

    def _build_page(self) -> None:
        self.page.title = "Salesforce Automation"
        self.page.window.width = 560
        self.page.window.height = 720
        self.page.window.resizable = False
        self.page.window.maximizable = False
        self.page.padding = 0
        self.page.spacing = 0
        self.page.bgcolor = "#F3F8FF"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.theme = ft.Theme(
            color_scheme_seed="#4F8FEA",
        )
        self.page.fonts = {
            "Poppins": "fonts/Poppins/Poppins.ttf",
            "OpenSans": "fonts/OpenSans/OpenSans.ttf",
        }

    def _build_controls(self) -> None:
        self.file_picker = ft.FilePicker(on_result=self._handle_file_pick_result)
        self.page.overlay.append(self.file_picker)

        self._on_browse: Optional[Callable[[str], None]] = None

        self.file_name_text = ft.Text(
            "לא נבחר קובץ",
            size=14,
            color="#5B6B85",
            text_align=ft.TextAlign.RIGHT,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        self.status_text = ft.Text(
            "",
            size=14,
            color="#F8FAFC",
            text_align=ft.TextAlign.CENTER,
            weight=ft.FontWeight.W_600,
            font_family="OpenSans",
        )

        self.progress_ring = ft.ProgressBar(
            width=280,
            value=0,
            color="#FFFFFF",
            bgcolor="#2E69C7",
            visible=False,
            bar_height=14,
            border_radius=8,
        )
        self.progress_label = ft.Text(
            "",
            size=13,
            color="#E2ECFF",
            visible=False,
            text_align=ft.TextAlign.CENTER,
        )

        self.run_button = ft.ElevatedButton(
            "הפעל",
            icon=ft.Icons.PLAY_ARROW_ROUNDED,
            width=180,
            height=48,
            style=self._primary_button_style(),
        )
        self.stop_button = ft.OutlinedButton(
            "עצור",
            icon=ft.Icons.STOP_CIRCLE_OUTLINED,
            width=180,
            height=48,
            visible=False,
            style=ft.ButtonStyle(
                color="#1D4F9E",
                side=ft.BorderSide(1, "#B8D0F8"),
                shape=ft.RoundedRectangleBorder(radius=14),
                bgcolor="#FFFFFF",
            ),
        )
        self.browse_button = ft.OutlinedButton(
            "בחר קובץ Excel",
            icon=ft.Icons.UPLOAD_FILE_ROUNDED,
            width=180,
            height=48,
            style=ft.ButtonStyle(
                color="#1D4F9E",
                side=ft.BorderSide(1, "#B8D0F8"),
                shape=ft.RoundedRectangleBorder(radius=14),
                bgcolor="#FFFFFF",
            ),
        )
        self.settings_button = ft.IconButton(
            icon=ft.Icons.SETTINGS_ROUNDED,
            icon_color="#FFFFFF",
            bgcolor="#2F6FD5",
            tooltip="הגדרות",
        )
        self.help_button = ft.IconButton(
            icon=ft.Icons.HELP_OUTLINE_ROUNDED,
            icon_color="#2F6FD5",
            bgcolor="#E9F1FF",
            tooltip="עזרה",
        )

    def _render(self) -> None:
        header = ft.Container(
            padding=ft.padding.symmetric(horizontal=28, vertical=26),
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_right,
                end=ft.alignment.bottom_left,
                colors=["#4F8FEA", "#2A5EB8"],
            ),
            content=ft.Column(
                spacing=18,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            self.help_button,
                            ft.Column(
                                spacing=4,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Text(
                                        "הגדרת משתמשים",
                                        size=28,
                                        weight=ft.FontWeight.W_700,
                                        color="#FFFFFF",
                                        font_family="Poppins",
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                    ft.Text(
                                        "salesforce",
                                        size=20,
                                        weight=ft.FontWeight.W_600,
                                        color="#DCE8FF",
                                        font_family="Poppins",
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                ],
                            ),
                            self.settings_button,
                        ],
                    ),
                    ft.Text(
                        "הרצת אוטומציה לקבצי Excel עם שליטה על מצב, עצירה והגדרות משתמש.",
                        size=14,
                        color="#E2ECFF",
                        text_align=ft.TextAlign.RIGHT,
                    ),
                ],
            ),
        )

        file_section = ft.Container(
            border_radius=18,
            bgcolor="#FFFFFF",
            padding=22,
            content=ft.Column(
                spacing=14,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(
                                "קובץ עבודה",
                                size=18,
                                weight=ft.FontWeight.W_700,
                                color="#1A2A42",
                            ),
                            ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, color="#4F8FEA"),
                        ],
                    ),
                    ft.Container(
                        border=ft.border.all(1, "#D8E5FB"),
                        border_radius=14,
                        padding=ft.padding.symmetric(horizontal=16, vertical=14),
                        bgcolor="#F8FBFF",
                        content=self.file_name_text,
                    ),
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[self.browse_button],
                    ),
                ],
            ),
        )

        actions_section = ft.Container(
            border_radius=18,
            bgcolor="#2F6FD5",
            padding=22,
            content=ft.Column(
                spacing=16,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        "ניהול הרצה",
                        size=18,
                        weight=ft.FontWeight.W_700,
                        color="#FFFFFF",
                    ),
                    ft.Text(
                        "הפעלה ועצירה בטוחה של תהליך האוטומציה.",
                        size=13,
                        color="#DCE8FF",
                        text_align=ft.TextAlign.CENTER,
                    ),
                    self.progress_ring,
                    self.progress_label,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.CENTER,
                        controls=[self.run_button, self.stop_button],
                    ),
                ],
            ),
        )

        status_section = ft.Container(
            border_radius=18,
            bgcolor="#163C75",
            padding=18,
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Text(
                        "סטטוס",
                        size=16,
                        weight=ft.FontWeight.W_700,
                        color="#FFFFFF",
                        text_align=ft.TextAlign.RIGHT,
                    ),
                    self.status_text,
                ],
            ),
        )

        content = ft.SafeArea(
            content=ft.Container(
                expand=True,
                padding=ft.padding.only(left=22, right=22, top=22, bottom=28),
                content=ft.Column(
                    spacing=18,
                    controls=[header, file_section, actions_section, status_section],
                ),
            )
        )

        self.page.add(content)
        self.page.update()

    def _primary_button_style(self) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            color="#1D4F9E",
            bgcolor="#FFFFFF",
            shape=ft.RoundedRectangleBorder(radius=14),
            overlay_color="#E6F0FF",
        )

    def bind_actions(
        self,
        on_browse: Callable[[str], None],
        on_run: Callable[[ft.ControlEvent], None],
        on_stop: Callable[[ft.ControlEvent], None],
        on_settings: Callable[[ft.ControlEvent], None],
        on_help: Callable[[ft.ControlEvent], None],
    ) -> None:
        self._on_browse = on_browse
        self.run_button.on_click = on_run
        self.stop_button.on_click = on_stop
        self.settings_button.on_click = on_settings
        self.help_button.on_click = on_help
        self.browse_button.on_click = self.pick_file

    def pick_file(self, _event: ft.ControlEvent | None = None) -> None:
        self.file_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["xlsx", "xls"],
            dialog_title="בחר קובץ Excel",
        )

    def _handle_file_pick_result(self, event: ft.FilePickerResultEvent) -> None:
        if not event.files:
            return
        file_path = event.files[0].path
        self.set_selected_file(file_path)
        if self._on_browse:
            self._on_browse(file_path)

    def set_selected_file(self, file_path: str | None) -> None:
        display_name = os.path.basename(file_path) if file_path else "לא נבחר קובץ"
        self.file_name_text.value = display_name
        self.file_name_text.tooltip = file_path or None
        self._safe_update()

    def set_status(self, text: str) -> None:
        self.status_text.value = text or ""
        self._safe_update()

    def set_progress(self, value: int) -> None:
        clamped = max(0, min(100, value))
        self.progress_ring.value = clamped / 100
        self.progress_label.value = f"{clamped}%"
        self._safe_update()

    def set_running(self, is_running: bool) -> None:
        self.run_button.visible = not is_running
        self.stop_button.visible = is_running
        self.progress_ring.visible = is_running
        self.progress_label.visible = is_running
        if is_running:
            self.stop_button.disabled = False
            self.set_progress(0)
        self._safe_update()

    def disable_stop(self) -> None:
        self.stop_button.disabled = True
        self._safe_update()

    def show_alert(self, title: str, message: str, level: str = "info") -> None:
        icon = {
            "warning": ft.Icons.WARNING_AMBER_ROUNDED,
            "error": ft.Icons.ERROR_OUTLINE_ROUNDED,
            "critical": ft.Icons.ERROR_OUTLINE_ROUNDED,
            "info": ft.Icons.INFO_OUTLINE_ROUNDED,
        }.get(level, ft.Icons.INFO_OUTLINE_ROUNDED)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                spacing=10,
                controls=[ft.Icon(icon, color="#2F6FD5"), ft.Text(title)],
            ),
            content=ft.Text(message, selectable=True),
            actions=[ft.TextButton("סגור", on_click=lambda _: self._close_dialog(dialog))],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)
        self._safe_update()

    def show_help_dialog(self) -> None:
        dialog = create_help_dialog(self.page)
        self.page.show_dialog(dialog)
        self._safe_update()

    def _close_dialog(self, dialog: ft.AlertDialog) -> None:
        dialog.open = False
        self.page.pop_dialog()
        self._safe_update()

    def _safe_update(self) -> None:
        with self._lock:
            self.page.update()
