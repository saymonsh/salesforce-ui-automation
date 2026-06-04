import asyncio
import os
import queue
import threading
from typing import Callable, Optional

import flet as ft

from src.core.config import config_instance as parm
from src.ui.help_dialog import create_help_dialog
from src.ui.theme import Color, Font, Radius, Space, Term, Type, apply_theme

# Map a debug-channel severity to its feed line color (the macOS terminal).
# "OUT"/"ERR" come from the raw stdout/stderr tee (chromedriver, tracebacks);
# the rest from the logger. Anything unmapped falls back to Term.TEXT.
_LEVEL_COLORS = {
    "ERROR": Term.ERROR, "ERR": Term.ERROR,
    "WARNING": Term.WARNING,
    "DEBUG": Term.DEBUG,
    "SUCCESS": Term.SUCCESS,
}

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BG_PATH = os.path.join(_ROOT, "assets", "icons", "bg.png")

_BG_OPACITY = 0.80
_GLASS_PANEL = ft.Colors.with_opacity(0.55, "#ffffff")
_GLASS_CHIP = ft.Colors.with_opacity(0.45, "#ffffff")
_GLASS_INSET = ft.Colors.with_opacity(0.38, "#ffffff")
_PANEL_SHADOW = ft.BoxShadow(
    blur_radius=44, spread_radius=0,
    color=ft.Colors.with_opacity(0.24, "#000000"), offset=ft.Offset(0, 16),
)

_PANEL_WIDTH = 440
_RING_TRACK = ft.Colors.with_opacity(0.14, "#2b2b2b")
_LINEAR_TRACK = ft.Colors.with_opacity(0.16, "#2b2b2b")


# Process types: key -> (label, icon). Drives the inline type selector and is
# the single source of truth for the Hebrew type names on the main window.
_TYPE_META = {
    "1": ("דיווח פעילות", ft.Icons.EDIT_NOTE_ROUNDED),
    "2": ("מועמדים", ft.Icons.GROUP_ROUNDED),
    "3": ("נוכחות", ft.Icons.FACT_CHECK_ROUNDED),
}


class MainView:
    def __init__(self, page: ft.Page):
        self.page = page
        self._lock = threading.RLock()
        self.settings_container = None
        self._settings_dialog = None
        self._feed_dialog = None
        self._logs_has_content = False
        self._running = False
        self._has_file = False
        self._on_run: Optional[Callable] = None
        self._on_stop: Optional[Callable] = None
        # Terminal output arrives from worker/chromedriver threads; queue it and
        # drain on the UI loop in batches (decoupled = no loop flooding/freeze).
        # Each item is (text, level) where level is a debug-channel severity.
        self._feed_q: "queue.Queue[tuple[str, str]]" = queue.Queue()
        # Plain-text mirror of the rendered feed lines — backs copy-all / save /
        # clear so they don't have to read back ft.Text controls. Capped alongside.
        self._feed_lines: list[str] = []

        self._build_page()
        self._build_controls()
        self._render()

    def _build_page(self) -> None:
        self.page.title = "כיוון — Salesforce Automation"
        # Restore size (used when the user un-maximizes); the app opens maximized.
        self.page.window.width = 600
        self.page.window.height = 712
        self.page.window.min_width = 540
        self.page.window.min_height = 640
        self.page.window.resizable = True
        self.page.window.maximized = True  # open full-screen by default
        # Hide the native Windows title bar — we build our own controls into the
        # glass panel. Resize borders are kept (not frameless).
        self.page.window.title_bar_hidden = True
        self.page.window.title_bar_buttons_hidden = True
        self.page.padding = 0
        self.page.spacing = 0
        apply_theme(self.page)

    def _build_controls(self) -> None:
        self.file_picker = ft.FilePicker()
        self.clipboard = ft.Clipboard()  # system clipboard for "copy all" in the feed
        self.page.services.append(self.file_picker)
        self.page.services.append(self.clipboard)
        self._on_browse: Optional[Callable[[str], None]] = None

        # --- Hero: a circular action button wrapped by a progress ring ----------
        self.progress_ring = ft.ProgressRing(
            value=0, width=160, height=160, stroke_width=8,
            color=Color.BRAND, bgcolor=_RING_TRACK,
        )
        # Two distinct glyphs swapped via Container.content — changing a single
        # ft.Icon.name alone does NOT re-render in Flet 0.84 (icon name caching),
        # so we swap the whole content instead (always re-renders).
        self.play_icon = ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, size=50, color=Color.TEXT_ON_BRAND)
        self.stop_icon = ft.Icon(ft.Icons.STOP_ROUNDED, size=46, color=Color.TEXT_ON_BRAND)
        self.action_circle = ft.Container(
            width=116, height=116, border_radius=Radius.PILL, bgcolor=Color.BRAND,
            alignment=ft.Alignment.CENTER, content=self.play_icon, ink=True,
            tooltip="הפעל תהליך", on_click=self._action_clicked,
            shadow=ft.BoxShadow(
                blur_radius=22, spread_radius=0,
                color=ft.Colors.with_opacity(0.35, Color.BRAND), offset=ft.Offset(0, 6),
            ),
        )
        self.hero_value = ft.Text("מוכן", size=26, weight=ft.FontWeight.W_800, color=Color.TEXT_PRIMARY)
        self.status_text = ft.Text(
            "מוכן להרצה", size=Type.BODY[0], color=Color.TEXT_SECONDARY,
            weight=ft.FontWeight.W_500, text_align=ft.TextAlign.CENTER,
            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True, expand=True,
        )
        self.counter_text = ft.Text("", size=Type.CAPTION[0], color=Color.TEXT_TERTIARY, weight=ft.FontWeight.W_600)
        # State dot inside the status field — color tracks idle/running/done/error.
        self.status_dot = ft.Container(width=9, height=9, border_radius=Radius.PILL, bgcolor=Color.TEXT_TERTIARY)
        # Slim progress footer pinned to the panel bottom — precise linear read
        # of the same value the ring shows.
        self.linear = ft.ProgressBar(
            value=0, color=Color.BRAND, bgcolor=_LINEAR_TRACK,
            bar_height=6, border_radius=Radius.PILL,
        )

        # --- Process-type inline selector ---------------------------------------
        self._type_segments: dict[str, ft.Container] = {}
        self._type_value = str(parm.TYPE) if parm.TYPE is not None else ""

        # --- File zone ----------------------------------------------------------
        self.file_badge = ft.Container(
            width=38, height=38, border_radius=Radius.PILL, alignment=ft.Alignment.CENTER,
            bgcolor=Color.BRAND_TINT,
            content=ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=20, color=Color.BRAND),
        )
        self.file_name_text = ft.Text(
            "לא נבחר קובץ", size=Type.BODY[0], color=Color.TEXT_PRIMARY,
            weight=ft.FontWeight.W_600, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True,
        )
        self.file_sub_text = ft.Text(
            "נדרש קובץ Excel", size=Type.CAPTION[0], color=Color.TEXT_TERTIARY,
            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
        )
        self.browse_button = ft.TextButton(
            "בחר קובץ", icon=ft.Icons.UPLOAD_FILE_ROUNDED,
            style=ft.ButtonStyle(color=Color.BRAND, padding=Space.SM),
        )

        # --- Chrome (topbar icons + window controls) ----------------------------
        self.help_button = ft.IconButton(ft.Icons.INFO_OUTLINE_ROUNDED, icon_color=Color.TEXT_SECONDARY, tooltip="עזרה")
        self.settings_button = ft.IconButton(ft.Icons.SETTINGS_ROUNDED, icon_color=Color.TEXT_SECONDARY, tooltip="הגדרות")

        self.win_min = ft.IconButton(
            ft.Icons.REMOVE, icon_size=18, icon_color=Color.TEXT_SECONDARY,
            tooltip="מזער", on_click=self._win_minimize,
        )
        self.win_max = ft.IconButton(
            ft.Icons.CROP_SQUARE_ROUNDED, icon_size=15, icon_color=Color.TEXT_SECONDARY,
            tooltip="הגדל / שחזר", on_click=self._win_maximize,
        )
        self.win_close = ft.IconButton(
            ft.Icons.CLOSE_ROUNDED, icon_size=18, icon_color=Color.TEXT_SECONDARY,
            tooltip="סגור", on_click=self._win_close,
            style=ft.ButtonStyle(overlay_color=ft.Colors.with_opacity(0.12, Color.DANGER)),
        )

        # Activity feed lives in its own pop-out dialog (opened from feed_button).
        # The list/holder are built once and persist so terminal lines keep
        # accumulating even while the dialog is closed.
        self.feed_button = ft.IconButton(
            ft.Icons.TERMINAL_ROUNDED, icon_color=Color.TEXT_SECONDARY, tooltip="זרם פעילות",
            on_click=lambda _: self.show_feed_dialog(),
        )
        self.logs_list = ft.ListView(
            expand=True, spacing=Space.XS, auto_scroll=True, on_scroll=self._on_feed_scroll,
        )
        # Toolbar handles set when the feed surface is built; let copy/save flash them.
        self.feed_copy_btn: Optional[ft.IconButton] = None
        self.feed_save_btn: Optional[ft.IconButton] = None
        self.logs_empty_view = ft.Container(
            alignment=ft.Alignment.CENTER, expand=True,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=Space.SM,
                controls=[
                    ft.Icon(ft.Icons.BOLT_ROUNDED, size=34, color="#9a9a9a"),
                    ft.Text("אין עדיין פעילות", color="#cfcfcf", italic=True),
                    ft.Text("בחר קובץ ולחץ על כפתור ההפעלה", color="#9a9a9a", size=Type.CAPTION[0]),
                ],
            ),
        )
        self.logs_holder = ft.Container(expand=True, content=self.logs_empty_view)

    # --------------------------------------------------------------- window controls
    def _win_minimize(self, e):
        self.page.window.minimized = True
        self._safe_update()

    def _win_maximize(self, e):
        self.page.window.maximized = not self.page.window.maximized
        self._safe_update()

    async def _win_close(self, e):
        # window.close() is a coroutine in Flet 0.84 — must be awaited.
        await self.page.window.close()

    # ------------------------------------------------------- process-type selector
    def _build_type_selector(self) -> ft.Container:
        segs: list[ft.Control] = []
        for key, (label, icon) in _TYPE_META.items():
            seg = ft.Container(
                data=key, expand=True, ink=True,
                border_radius=Radius.MD,
                padding=ft.padding.symmetric(vertical=Space.SM, horizontal=Space.XS),
                alignment=ft.Alignment.CENTER,
                on_click=self._type_clicked,
                tooltip=f"סוג {key} · {label}",
                content=ft.Column(
                    spacing=3, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(icon, size=18),
                        ft.Text(label, size=Type.CAPTION[0], weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER),
                    ],
                ),
            )
            self._type_segments[key] = seg
            segs.append(seg)
        bar = ft.Container(
            bgcolor=_GLASS_INSET, border_radius=Radius.LG, padding=4,
            content=ft.Row(spacing=4, controls=segs),
        )
        self._style_type_segments()  # initial look only — not mounted yet, no update()
        return bar

    def _style_type_segments(self) -> None:
        for key, seg in self._type_segments.items():
            on = key == self._type_value
            seg.bgcolor = Color.BRAND if on else ft.Colors.TRANSPARENT
            icon, text = seg.content.controls
            icon.color = Color.TEXT_ON_BRAND if on else Color.TEXT_SECONDARY
            text.color = Color.TEXT_ON_BRAND if on else Color.TEXT_SECONDARY
            text.weight = ft.FontWeight.W_700 if on else ft.FontWeight.W_600

    def _type_clicked(self, e: ft.ControlEvent) -> None:
        if self._running:
            return  # don't switch process mid-run
        key = e.control.data
        if key == self._type_value:
            return
        self._type_value = key
        self._style_type_segments()
        try:
            parm.update_config("Salesforce", "TYPE", key)
        except Exception as ex:  # pragma: no cover - disk/parse failure
            self.show_alert("שגיאה", f"שמירת סוג התהליך נכשלה:\n{ex}", "error")
            return
        label = _TYPE_META.get(key, ("", None))[0]
        self.status_text.value = f"מצב: {label}"
        self.status_text.color = Color.TEXT_SECONDARY
        self.hero_value.value, self.hero_value.color = "מוכן", Color.TEXT_PRIMARY
        self._safe_update()

    def _refresh_type(self) -> None:
        """Re-sync the selector after the settings dialog may have changed TYPE."""
        self._type_value = str(parm.TYPE) if parm.TYPE is not None else ""
        self._style_type_segments()

    # ------------------------------------------------------------------ file zone
    def _build_file_zone(self) -> ft.Container:
        return ft.Container(
            bgcolor=_GLASS_CHIP, border_radius=Radius.LG,
            border=ft.border.all(1, ft.Colors.with_opacity(0.5, "#ffffff")),
            padding=ft.padding.symmetric(horizontal=Space.MD, vertical=Space.SM),
            content=ft.Row(
                spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    self.file_badge,
                    ft.Column(
                        spacing=0, expand=True, tight=True,
                        controls=[self.file_name_text, self.file_sub_text],
                    ),
                    self.browse_button,
                ],
            ),
        )

    # ------------------------------------------------------------------ hero
    def _build_hero(self) -> ft.Control:
        ring = ft.Stack(
            width=160, height=160, alignment=ft.Alignment.CENTER,
            controls=[self.progress_ring, self.action_circle],
        )
        # Status lives in a dedicated glass field (dot + live label), not loose
        # text. Fixed width so long console lines truncate instead of stretching.
        status_field = ft.Container(
            width=360, bgcolor=_GLASS_INSET, border_radius=Radius.PILL,
            border=ft.border.all(1, ft.Colors.with_opacity(0.5, "#ffffff")),
            padding=ft.padding.symmetric(horizontal=Space.MD, vertical=Space.XS + 2),
            content=ft.Row(
                spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[self.status_dot, self.status_text],
            ),
        )
        # Full-width Row (max main-axis) centers the hero block horizontally
        # regardless of the parent Column's cross-axis alignment (RTL-safe).
        return ft.Container(
            expand=True,
            content=ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=Space.MD,
                        controls=[
                            ring,
                            self.hero_value,
                            status_field,
                            self.counter_text,
                        ],
                    ),
                ],
            ),
        )

    # ------------------------------------------------------------------ feed surface
    def _build_feed_surface(self):
        """A macOS-style terminal window for the activity (debug) feed.

        Dark rounded body, a traffic-light title bar (the red light closes the
        window), monospace lines, and a toolbar to copy/clear/save the stream.
        Wraps the persistent logs_holder so history survives dialog open/close.
        """
        def light(color: str, on_click=None, tip: str | None = None) -> ft.Container:
            return ft.Container(
                width=12, height=12, border_radius=Radius.PILL, bgcolor=color,
                on_click=on_click, tooltip=tip, ink=on_click is not None,
            )

        lights = ft.Row(spacing=Space.SM, controls=[
            light(Term.DOT_RED, on_click=lambda _: self._close_feed_dialog(), tip="סגור"),
            light(Term.DOT_YELLOW),
            light(Term.DOT_GREEN),
        ])

        def tool(icon, tip, handler, color=Term.TITLE) -> ft.IconButton:
            return ft.IconButton(icon, icon_color=color, icon_size=18, tooltip=tip,
                                 on_click=lambda _: handler())

        self.feed_copy_btn = tool(ft.Icons.COPY_ALL_ROUNDED, "העתק הכל", self._copy_feed)
        self.feed_save_btn = tool(ft.Icons.SAVE_ALT_ROUNDED, "שמור ללוג", self._save_feed)
        toolbar = ft.Row(spacing=0, tight=True, controls=[
            self.feed_copy_btn,
            tool(ft.Icons.DELETE_SWEEP_ROUNDED, "נקה", self._clear_feed),
            self.feed_save_btn,
            # Explicit close, in addition to the red traffic light.
            tool(ft.Icons.CLOSE_ROUNDED, "סגור", self._close_feed_dialog),
        ])

        title = ft.Row(
            spacing=Space.SM, alignment=ft.MainAxisAlignment.CENTER, controls=[
                ft.Icon(ft.Icons.TERMINAL_ROUNDED, size=15, color=Term.TITLE),
                ft.Text("זרם פעילות — Activity", size=Type.CAPTION[0],
                        weight=ft.FontWeight.W_600, color=Term.TITLE, font_family=Font.MONO),
            ],
        )
        titlebar = ft.Container(
            bgcolor=Term.TITLEBAR,
            border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.08, Term.HAIRLINE))),
            padding=ft.padding.symmetric(horizontal=Space.MD, vertical=Space.XS),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[lights, ft.Container(expand=True, content=title), toolbar],
            ),
        )
        body = ft.Container(
            expand=True, bgcolor=Term.BG,
            padding=ft.padding.symmetric(horizontal=Space.LG, vertical=Space.MD),
            content=self.logs_holder,
        )
        return ft.Container(
            expand=True, border_radius=Radius.LG, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            border=ft.border.all(1, ft.Colors.with_opacity(0.5, Term.BORDER)), shadow=_PANEL_SHADOW,
            content=ft.Column(spacing=0, expand=True, controls=[titlebar, body]),
        )

    # --------------------------------------------------------------- feed toolbar
    def _on_feed_scroll(self, e) -> None:
        """Pause auto-scroll while the user is reading higher up; resume at bottom."""
        if e.max_scroll_extent <= 0:
            return
        at_bottom = (e.max_scroll_extent - e.pixels) < 48
        if self.logs_list.auto_scroll != at_bottom:
            self.logs_list.auto_scroll = at_bottom  # applies on the next appended line

    async def _flash_btn(self, btn, icon, color, tip, rest_icon, rest_tip) -> None:
        """Briefly swap a toolbar icon to confirm an action (no popup alert)."""
        if btn is None:
            return
        btn.icon, btn.icon_color, btn.tooltip = icon, color, tip
        self._safe_update()
        await asyncio.sleep(1.4)
        # The dialog may have closed/reopened (new button) meanwhile — only restore ours.
        if btn.icon == icon:
            btn.icon, btn.icon_color, btn.tooltip = rest_icon, Term.TITLE, rest_tip
            self._safe_update()

    def _copy_feed(self) -> None:
        if not self._feed_lines:
            return
        self.page.run_task(self._copy_feed_async, "\n".join(self._feed_lines))

    async def _copy_feed_async(self, text: str) -> None:
        try:
            await self.clipboard.set(text)
        except Exception:
            return
        await self._flash_btn(self.feed_copy_btn, ft.Icons.CHECK_ROUNDED, Term.SUCCESS,
                              "הועתק!", ft.Icons.COPY_ALL_ROUNDED, "העתק הכל")

    def _clear_feed(self) -> None:
        self._feed_lines.clear()
        self.logs_list.controls.clear()
        self._logs_has_content = False
        self.logs_holder.content = self.logs_empty_view
        self._safe_update()

    def _save_feed(self) -> None:
        if not self._feed_lines:
            return
        self.page.run_task(self._save_feed_async)

    async def _save_feed_async(self) -> None:
        path = await self.file_picker.save_file(
            dialog_title="שמירת זרם הפעילות", file_name="activity-log.txt",
            file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["txt", "log"],
        )
        if not path:
            return
        # Inline button feedback only — never a popup, so it doesn't break the
        # "no alerts while the console is open" rule.
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(self._feed_lines) + "\n")
        except Exception:  # pragma: no cover - disk failure
            await self._flash_btn(self.feed_save_btn, ft.Icons.ERROR_OUTLINE_ROUNDED, Term.ERROR,
                                  "השמירה נכשלה", ft.Icons.SAVE_ALT_ROUNDED, "שמור ללוג")
            return
        await self._flash_btn(self.feed_save_btn, ft.Icons.CHECK_ROUNDED, Term.SUCCESS,
                              "נשמר!", ft.Icons.SAVE_ALT_ROUNDED, "שמור ללוג")

    def _build_console_panel(self):
        topbar = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Row(spacing=Space.MD, controls=[
                    ft.Image(src="/icons/kivun_mark.svg", width=34, height=34),
                    ft.Text("כיוון", size=20, weight=ft.FontWeight.W_700, color=Color.BRAND),
                ]),
                ft.Row(spacing=Space.XS, controls=[self.feed_button, self.settings_button, self.help_button]),
            ],
        )
        return ft.Container(
            width=_PANEL_WIDTH, margin=ft.margin.only(top=Space.XS, bottom=Space.XXL),
            bgcolor=_GLASS_PANEL, border=ft.border.all(1, ft.Colors.with_opacity(0.55, "#ffffff")),
            border_radius=24, shadow=_PANEL_SHADOW, padding=Space.XL,
            content=ft.Column(
                spacing=Space.LG, expand=True,
                controls=[
                    topbar,
                    ft.Divider(color=ft.Colors.with_opacity(0.5, Color.BORDER), height=1),
                    self._build_type_selector(),
                    self._build_file_zone(),
                    self._build_hero(),
                    self.linear,
                ],
            ),
        )

    def _build_chrome(self):
        """A thin window-chrome strip ON THE BACKGROUND (above the panel):
        a centered drag handle + window controls at the top-right. The native
        title bar is hidden."""
        # Subtle, translucent window controls — top-right (Windows convention).
        controls = ft.Container(
            bgcolor=ft.Colors.with_opacity(0.45, "#ffffff"),
            border_radius=Radius.PILL,
            padding=ft.padding.symmetric(horizontal=Space.XS),
            content=ft.Row(spacing=0, tight=True, controls=[self.win_min, self.win_max, self.win_close]),
        )
        # A clearly-marked drag handle in the centre.
        drag_handle = ft.Container(
            bgcolor=ft.Colors.with_opacity(0.20, "#ffffff"),
            border_radius=Radius.PILL,
            padding=ft.padding.symmetric(horizontal=Space.LG, vertical=2),
            tooltip="גרור להזזת החלון",
            content=ft.Icon(ft.Icons.DRAG_HANDLE_ROUNDED, size=18,
                            color=ft.Colors.with_opacity(0.65, "#000000")),
        )
        return ft.WindowDragArea(
            maximizable=True,
            content=ft.Container(
                # proper distance from the top window border
                padding=ft.padding.only(top=Space.MD, left=Space.LG, right=Space.LG, bottom=Space.SM),
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[drag_handle, controls],  # RTL: drag → right corner, controls → left
                ),
            ),
        )

    def _render(self) -> None:
        console = ft.Row(
            expand=True, alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[self._build_console_panel()],
        )
        # Kept so the settings dialog can hide the main panel while open — that
        # way the translucent dialog sits directly over the background.
        self._console_row = console
        # Chrome strip on the background, panel below it.
        content = ft.Column(expand=True, spacing=0, controls=[self._build_chrome(), console])

        if os.path.exists(_BG_PATH):
            bg_layer = ft.Image(src="/icons/bg.png", fit=ft.BoxFit.COVER, opacity=_BG_OPACITY,
                                left=0, top=0, right=0, bottom=0)
            root = ft.Stack(expand=True, controls=[bg_layer, content])
        else:
            root = content
        self.page.add(root)
        self.page.update()
        self.page.run_task(self._drain_feed)  # start the activity-feed drainer

    # --------------------------------------------------------------- actions
    def _action_clicked(self, e):
        if self._running:
            if self._on_stop:
                self._on_stop(e)
        elif self._on_run:
            self._on_run(e)

    def bind_actions(self, on_browse, on_run, on_stop, on_settings, on_help) -> None:
        self._on_browse = on_browse
        self._on_run = on_run
        self._on_stop = on_stop
        self.settings_button.on_click = on_settings
        self.help_button.on_click = on_help
        self.browse_button.on_click = self.pick_file

    def pick_file(self, _event=None) -> None:
        self.page.run_task(self._pick_file_async)

    async def _pick_file_async(self) -> None:
        files = await self.file_picker.pick_files(
            allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx", "xls"], dialog_title="בחר קובץ Excel",
        )
        self._handle_file_pick_result(files)

    def _handle_file_pick_result(self, files) -> None:
        if not files:
            return
        file_path = files[0].path or files[0].name
        self.set_selected_file(file_path)
        if self._on_browse:
            self._on_browse(file_path)

    def set_selected_file(self, file_path: str | None) -> None:
        self._has_file = bool(file_path)
        if file_path:
            self.file_name_text.value = os.path.basename(file_path)
            self.file_name_text.tooltip = file_path
            self.file_sub_text.value = "קובץ נבחר · מוכן להרצה"
            self.file_sub_text.color = Color.SUCCESS
            self.file_badge.bgcolor = ft.Colors.with_opacity(0.18, Color.SUCCESS)
            self.file_badge.content.name = ft.Icons.TASK_ALT_ROUNDED
            self.file_badge.content.color = Color.SUCCESS
        else:
            self.file_name_text.value = "לא נבחר קובץ"
            self.file_name_text.tooltip = None
            self.file_sub_text.value = "נדרש קובץ Excel"
            self.file_sub_text.color = Color.TEXT_TERTIARY
            self.file_badge.bgcolor = Color.BRAND_TINT
            self.file_badge.content.name = ft.Icons.DESCRIPTION_OUTLINED
            self.file_badge.content.color = Color.BRAND
        self._safe_update()

    def set_status(self, text: str, level: str | None = None) -> None:
        """Updates the hero state/caption only. The feed shows real terminal output."""
        if not text:
            return
        self.status_text.value = text
        is_error = level == "error" or "error" in text.lower() or "שגיאה" in text
        if is_error:
            self.status_text.color = self.hero_value.color = Color.DANGER
            self.progress_ring.color = self.linear.color = Color.DANGER
            self.status_dot.bgcolor = Color.DANGER
            self.hero_value.value = "שגיאה"
        elif level == "success":
            self.status_text.color = self.hero_value.color = Color.SUCCESS
            self.progress_ring.color = self.linear.color = Color.SUCCESS
            self.progress_ring.value = self.linear.value = 1
            self.status_dot.bgcolor = Color.SUCCESS
            self.action_circle.bgcolor = Color.SUCCESS
            self.action_circle.shadow.color = ft.Colors.with_opacity(0.35, Color.SUCCESS)
            self.action_circle.content = self.play_icon  # run finished → idle triangle
            self.hero_value.value = "הושלם"
        elif level == "warning":
            # Work completed but a manual action is still required (TYPE 2 end
            # state). Amber, full ring, but distinct from a clean success.
            self.status_text.color = self.hero_value.color = Color.WARNING
            self.progress_ring.color = self.linear.color = Color.WARNING
            self.progress_ring.value = self.linear.value = 1
            self.status_dot.bgcolor = Color.WARNING
            self.action_circle.content = self.play_icon
            self.hero_value.value = "נדרשת פעולה"
        else:
            self.status_text.color = Color.TEXT_SECONDARY
            self.status_dot.bgcolor = Color.BRAND if self._running else Color.TEXT_TERTIARY
        self._safe_update()

    # Called from any thread (worker log channel / stdout-stderr tee / chromedriver
    # pump). Thread-safe, cheap. `level` is a debug-channel severity; the legacy
    # `is_err` bool maps to "ERR"/"OUT" for the raw stdout/stderr tee.
    def enqueue_terminal_line(self, text: str, is_err: bool = False, level: str | None = None) -> None:
        lvl = level or ("ERR" if is_err else "OUT")
        try:
            self._feed_q.put_nowait((text, lvl))
        except Exception:
            pass

    async def _drain_feed(self) -> None:
        """Single UI-loop task: batch-drain the queue into the feed every 200ms."""
        while True:
            await asyncio.sleep(0.2)
            batch = []
            try:
                while len(batch) < 300:
                    batch.append(self._feed_q.get_nowait())
            except queue.Empty:
                pass
            if not batch:
                continue
            if not self._logs_has_content:
                self.logs_holder.content = self.logs_list
                self._logs_has_content = True
            for text, level in batch:
                self.logs_list.controls.append(ft.Text(
                    text, color=_LEVEL_COLORS.get(level, Term.TEXT),
                    size=Type.CAPTION[0], font_family=Font.MONO,
                    text_align=ft.TextAlign.LEFT, selectable=True))
                self._feed_lines.append(text)  # plain-text mirror for copy/save
            if len(self.logs_list.controls) > 600:  # cap history (both views in lockstep)
                del self.logs_list.controls[:-600]
                del self._feed_lines[:-600]
            # No status mirroring here: the status field is driven solely by the
            # clean status channel (issue #12). The feed is the debug channel.
            self._safe_update()

    def set_progress(self, value: float, current: int | None = None, total: int | None = None) -> None:
        clamped = max(0.0, min(1.0, value))
        self.progress_ring.value = clamped
        self.linear.value = clamped
        if total:
            self.counter_text.value = f"{current or 0} מתוך {total} רשומות"
        if self._running:
            self.hero_value.value = f"{int(clamped * 100)}%"
            self.hero_value.color = Color.TEXT_PRIMARY
        self._safe_update()

    def set_running(self, is_running: bool) -> None:
        self._running = is_running
        self.action_circle.disabled = False  # re-enable after a stop/finish cycle
        # Draw the eye to the feed button while output is streaming.
        self.feed_button.icon_color = Color.BRAND if is_running else Color.TEXT_SECONDARY
        if is_running:
            self.action_circle.bgcolor = Color.DANGER
            self.action_circle.shadow.color = ft.Colors.with_opacity(0.35, Color.DANGER)
            self.action_circle.content = self.stop_icon  # square while running
            self.action_circle.tooltip = "עצור תהליך"
            self.progress_ring.color = self.linear.color = Color.BRAND
            self.progress_ring.value = self.linear.value = 0
            self.status_dot.bgcolor = Color.BRAND
            self.hero_value.value, self.hero_value.color = "0%", Color.TEXT_PRIMARY
            self.counter_text.value = ""
            # Dim the type selector — switching process mid-run is blocked.
            for seg in self._type_segments.values():
                seg.opacity = 0.55 if seg.data != self._type_value else 1.0
        else:
            self.action_circle.bgcolor = Color.BRAND
            self.action_circle.shadow.color = ft.Colors.with_opacity(0.35, Color.BRAND)
            self.action_circle.content = self.play_icon  # triangle when idle
            self.action_circle.tooltip = "הפעל תהליך"
            self.status_dot.bgcolor = Color.TEXT_TERTIARY
            for seg in self._type_segments.values():
                seg.opacity = 1.0
        self._safe_update()

    def disable_stop(self) -> None:
        self.action_circle.disabled = True
        self._safe_update()

    # ------------------------------------------------------------- feed pop-out
    def show_feed_dialog(self) -> None:
        """Open the activity feed as a standalone macOS-style terminal window."""
        if self._feed_dialog is not None:
            return  # already open
        self._feed_dialog = ft.AlertDialog(
            modal=False,
            rtl=True,
            bgcolor=ft.Colors.TRANSPARENT,  # the terminal surface brings its own dark chrome
            barrier_color=ft.Colors.with_opacity(0.28, "#000000"),
            shape=ft.RoundedRectangleBorder(radius=Radius.LG),
            content_padding=0,
            on_dismiss=lambda _: self._on_feed_dismissed(),
            content=ft.Container(
                width=1040, height=580, rtl=True,
                content=self._build_feed_surface(),
            ),
        )
        self.page.show_dialog(self._feed_dialog)
        self._safe_update()

    def _close_feed_dialog(self) -> None:
        if self._feed_dialog is not None:
            self._feed_dialog.open = False
            self.page.pop_dialog()
            self._feed_dialog = None
        self._safe_update()

    def _on_feed_dismissed(self) -> None:
        # Barrier/Esc dismissal: just drop our reference (Flet already closed it).
        self._feed_dialog = None

    # ------------------------------------------------------------- settings modal
    def show_settings_view(self, settings_container) -> None:
        self.settings_container = settings_container
        close_btn = ft.IconButton(
            ft.Icons.CLOSE_ROUNDED, icon_color=Color.TEXT_SECONDARY, icon_size=20,
            tooltip="סגור", on_click=lambda _: self.switch_to_main(),
        )
        self._settings_dialog = ft.AlertDialog(
            modal=True,
            rtl=True,
            # Translucent glass surface. The main panel is hidden while the
            # dialog is open (see show_settings_view), so the background shows
            # through the glass with nothing wedged between them.
            bgcolor=ft.Colors.with_opacity(0.62, "#ffffff"),
            barrier_color=ft.Colors.with_opacity(0.06, "#000000"),
            shape=ft.RoundedRectangleBorder(radius=Radius.LG),
            content_padding=0,
            content=ft.Container(
                width=900, height=620, rtl=True,  # ensure the whole dialog lays out RTL
                border=ft.border.all(1, ft.Colors.with_opacity(0.6, "#ffffff")),
                border_radius=Radius.LG,
                content=ft.Column(
                    spacing=0,
                    controls=[
                        # X close in the corner (RTL END → left edge), with breathing room
                        ft.Container(
                            padding=ft.padding.only(top=Space.SM, left=Space.SM, right=Space.SM),
                            content=ft.Row([close_btn], alignment=ft.MainAxisAlignment.END),
                        ),
                        ft.Container(expand=True, content=settings_container),
                    ],
                ),
            ),
        )
        # Hide the main panel so only the background sits behind the glass dialog.
        if getattr(self, "_console_row", None) is not None:
            self._console_row.visible = False
        self.page.show_dialog(self._settings_dialog)
        self._safe_update()

    def switch_to_main(self) -> None:
        if self._settings_dialog is not None:
            self._settings_dialog.open = False
            self.page.pop_dialog()
            self._settings_dialog = None
        # Restore the main panel that was hidden while settings were open.
        if getattr(self, "_console_row", None) is not None:
            self._console_row.visible = True
        self._refresh_type()
        self._safe_update()

    def show_alert(self, title: str, message: str, level: str = "info") -> None:
        # While the console terminal is open it owns the screen — errors already
        # stream into it as ERR lines, so don't stack popup alerts on top of it.
        if self._feed_dialog is not None:
            return
        icon = {
            "warning": ft.Icons.WARNING_AMBER_ROUNDED, "error": ft.Icons.ERROR_OUTLINE_ROUNDED,
            "critical": ft.Icons.ERROR_OUTLINE_ROUNDED, "info": ft.Icons.INFO_OUTLINE_ROUNDED,
        }.get(level, ft.Icons.INFO_OUTLINE_ROUNDED)
        icon_color = Color.DANGER if level in ("error", "critical") else Color.BRAND
        dialog = ft.AlertDialog(
            modal=True,
            # Dialogs render in an overlay that does NOT inherit page.rtl, so set
            # it explicitly — otherwise mixed Hebrew/Latin text (e.g. "…ל-VPN")
            # wraps and aligns as LTR. Matches the settings/feed dialogs.
            rtl=True,
            title=ft.Row(spacing=Space.SM, controls=[ft.Icon(icon, color=icon_color), ft.Text(title, color=Color.TEXT_PRIMARY)]),
            content=ft.Text(message, selectable=True, color=Color.TEXT_PRIMARY, text_align=ft.TextAlign.RIGHT),
            actions=[ft.TextButton("סגור", on_click=lambda _: self._close_dialog(dialog))],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)
        self._safe_update()

    def show_help_dialog(self) -> None:
        self.page.show_dialog(create_help_dialog(self.page))
        self._safe_update()

    def _close_dialog(self, dialog: ft.AlertDialog) -> None:
        dialog.open = False
        self.page.pop_dialog()
        self._safe_update()

    def _safe_update(self) -> None:
        with self._lock:
            if self.page:
                self.page.update()
