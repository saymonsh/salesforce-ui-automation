import os
import threading
from typing import Callable, Optional

import flet as ft

from src.ui.help_dialog import create_help_dialog
from src.ui.components.progress_bar import ProgressBar

class MainView:
    def __init__(self, page: ft.Page):
        self.page = page
        self._lock = threading.RLock()
        self.current_nav = "main" # 'main', 'logs', 'settings'
        self.settings_container = None
        
        self._build_page()
        self._build_controls()
        self._render()

    def _build_page(self) -> None:
        self.page.title = "Salesforce Automation"
        self.page.window.width = 900
        self.page.window.height = 700
        self.page.window.resizable = True
        self.page.padding = 0
        self.page.spacing = 0
        self.page.bgcolor = "#f4f4f4"
        self.page.theme_mode = ft.ThemeMode.LIGHT

    def _build_controls(self) -> None:
        self.file_picker = ft.FilePicker()
        self.page.services.append(self.file_picker)

        self._on_browse: Optional[Callable[[str], None]] = None
        self._on_settings_click: Optional[Callable[[ft.ControlEvent], None]] = None

        # --- Main Execution Controls ---
        self.status_text = ft.Text(
            "מוכן",
            size=16,
            color="#828383",
            weight=ft.FontWeight.W_600,
        )

        self.file_name_text = ft.Text(
            "לא נבחר קובץ",
            size=14,
            color="#000000",
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        self.browse_button = ft.OutlinedButton(
            "בחר קובץ",
            icon=ft.Icons.UPLOAD_FILE_ROUNDED,
            style=ft.ButtonStyle(
                color="#828383",
                side=ft.BorderSide(1, "#828383"),
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=20,
            ),
        )

        self.run_button = ft.FilledButton(
            "הפעל",
            icon=ft.Icons.PLAY_ARROW_ROUNDED,
            style=ft.ButtonStyle(
                bgcolor="#de2952",
                color="#ffffff",
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=20,
            ),
            expand=True,
        )

        self.stop_button = ft.OutlinedButton(
            "עצור תהליך",
            icon=ft.Icons.STOP_CIRCLE_OUTLINED,
            style=ft.ButtonStyle(
                color="#f27894",
                side=ft.BorderSide(2, "#f27894"),
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=20,
            ),
            visible=False,
            expand=True,
        )

        self.progress_bar = ProgressBar()
        self.progress_bar.visible = False

        self.help_button = ft.IconButton(
            icon=ft.Icons.HELP_OUTLINE_ROUNDED,
            icon_color="#828383",
            tooltip="עזרה",
        )

        # --- Live Logs Controls ---
        self.logs_list = ft.ListView(expand=True, spacing=5, auto_scroll=True)

        # --- Navigation Controls ---
        self.nav_main = self._create_nav_button("Main Execution", "main", ft.Icons.PLAY_ARROW_ROUNDED)
        self.nav_logs = self._create_nav_button("Live Logs", "logs", ft.Icons.TERMINAL_ROUNDED)
        self.nav_settings = self._create_nav_button("Settings", "settings", ft.Icons.SETTINGS_ROUNDED)

    def _create_nav_button(self, text, nav_id, icon):
        return ft.Container(
            content=ft.Row([
                ft.Icon(icon, color="#de2952" if self.current_nav == nav_id else "#828383"),
                ft.Text(text, color="#de2952" if self.current_nav == nav_id else "#000000", weight=ft.FontWeight.W_600)
            ]),
            padding=15,
            border_radius=8,
            bgcolor="#f4f4f4" if self.current_nav == nav_id else ft.Colors.TRANSPARENT,
            ink=True,
            on_click=lambda e: self._on_nav_click(nav_id)
        )

    def _update_nav_styles(self):
        navs = {
            "main": self.nav_main,
            "logs": self.nav_logs,
            "settings": self.nav_settings
        }
        for nav_id, container in navs.items():
            is_active = (self.current_nav == nav_id)
            container.bgcolor = "#f4f4f4" if is_active else ft.Colors.TRANSPARENT
            row = container.content
            row.controls[0].color = "#de2952" if is_active else "#828383"
            row.controls[1].color = "#de2952" if is_active else "#000000"

    def _on_nav_click(self, nav_id):
        if nav_id == "settings" and self._on_settings_click:
            self._on_settings_click(None)
        else:
            self.current_nav = nav_id
            self._update_nav_styles()
            self._switch_view()

    def show_settings_view(self, settings_container):
        self.settings_container = settings_container
        self.current_nav = "settings"
        self._update_nav_styles()
        self._switch_view()

    def switch_to_main(self):
        self.current_nav = "main"
        self._update_nav_styles()
        self._switch_view()

    def _build_main_execution_view(self):
        status_card = ft.Card(
            elevation=2,
            bgcolor="#ffffff",
            content=ft.Container(
                padding=20,
                content=ft.Row(
                    controls=[self.status_text, self.help_button],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                )
            )
        )

        file_card = ft.Card(
            elevation=2,
            bgcolor="#ffffff",
            content=ft.Container(
                padding=20,
                content=ft.Column(
                    spacing=15,
                    controls=[
                        ft.Container(
                            border=ft.border.all(1, "#828383"),
                            border_radius=8,
                            padding=20,
                            content=ft.Column([
                                ft.Row([self.browse_button], alignment=ft.MainAxisAlignment.CENTER),
                                ft.Row([self.file_name_text], alignment=ft.MainAxisAlignment.CENTER)
                            ], spacing=10)
                        )
                    ]
                )
            )
        )

        action_card = ft.Card(
            elevation=2,
            bgcolor="#ffffff",
            content=ft.Container(
                padding=20,
                content=ft.Column(
                    spacing=15,
                    controls=[
                        ft.Row([self.run_button, self.stop_button], spacing=15),
                        ft.Container(content=self.progress_bar, padding=ft.padding.only(top=10))
                    ]
                )
            )
        )

        return ft.Container(
            padding=20,
            expand=True,
            content=ft.Column(
                spacing=15,
                controls=[status_card, file_card, action_card]
            )
        )

    def _build_live_logs_view(self):
        return ft.Container(
            padding=20,
            expand=True,
            bgcolor="#000000",
            content=self.logs_list
        )

    def _render(self) -> None:
        self.main_view_container = self._build_main_execution_view()
        self.logs_view_container = self._build_live_logs_view()
        
        self.content_area = ft.Container(
            expand=True,
            content=self.main_view_container
        )

        self.sidebar = ft.Container(
            width=250,
            bgcolor="#ffffff",
            border=ft.border.only(left=ft.BorderSide(1, "#e0e0e0")),
            padding=20,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Text("Salesforce Automation", size=18, weight=ft.FontWeight.BOLD, color="#000000"),
                    ft.Divider(color="#828383"),
                    self.nav_main,
                    self.nav_settings,
                    self.nav_logs
                ]
            )
        )

        main_row = ft.Row(
            expand=True,
            controls=[
                self.content_area,
                self.sidebar
            ]
        )

        self.page.add(main_row)
        self.page.update()

    def _switch_view(self):
        if self.current_nav == "main":
            self.content_area.content = self.main_view_container
        elif self.current_nav == "logs":
            self.content_area.content = self.logs_view_container
        elif self.current_nav == "settings":
            if self.settings_container:
                self.content_area.content = self.settings_container
            else:
                self.content_area.content = ft.Text("Loading Settings...")
        
        self._safe_update()

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
        self._on_settings_click = on_settings
        self.help_button.on_click = on_help
        self.browse_button.on_click = self.pick_file

    def pick_file(self, _event: ft.ControlEvent | None = None) -> None:
        self.page.run_task(self._pick_file_async)

    async def _pick_file_async(self) -> None:
        files = await self.file_picker.pick_files(
            allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx", "xls"],
            dialog_title="בחר קובץ Excel",
        )
        self._handle_file_pick_result(files)

    def _handle_file_pick_result(self, files: list[ft.FilePickerFile] | None) -> None:
        if not files:
            return
        file_path = files[0].path or files[0].name
        self.set_selected_file(file_path)
        if self._on_browse:
            self._on_browse(file_path)

    def set_selected_file(self, file_path: str | None) -> None:
        display_name = os.path.basename(file_path) if file_path else "לא נבחר קובץ"
        self.file_name_text.value = display_name
        self.file_name_text.tooltip = file_path or None
        self._safe_update()

    def set_status(self, text: str) -> None:
        if not text:
            return
            
        self.status_text.value = text
        
        if "error" in text.lower() or "שגיאה" in text:
            self.status_text.color = "#f27894"
        else:
            self.status_text.color = "#828383"
            
        log_text = ft.Text(text, color="#ffffff", size=13, font_family="Consolas")
        self.logs_list.controls.append(log_text)
        
        self._safe_update()

    def set_progress(self, value: float) -> None:
        self.progress_bar.update_progress(value)

    def set_running(self, is_running: bool) -> None:
        self.run_button.visible = not is_running
        self.stop_button.visible = is_running
        self.progress_bar.visible = is_running
        
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
                controls=[ft.Icon(icon, color="#de2952"), ft.Text(title, color="#000000")],
            ),
            content=ft.Text(message, selectable=True, color="#000000"),
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
            if self.page:
                self.page.update()
