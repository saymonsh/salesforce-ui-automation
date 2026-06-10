import asyncio
import base64
import os
import queue
import subprocess
import threading
from typing import Callable, Optional

import flet as ft

from src.automation.win_window import (
    BrowserOverlay,
    close_window,
    find_window_by_title,
    host_metrics,
    set_process_dpi_aware,
    window_pid,
)
from src.core.constants import APP_WINDOW_TITLE
from src.core.config import config_instance as parm
from src.core.status_messages import Status
from src.core.utils import ltr_isolate
from src.ui.data_grid import DataGridView
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

# Insets (in Flet LOGICAL px) of the live-browser rectangle (browser_body) inside
# the maximized window, used to place the owned-overlay Chrome (issue #19). These
# MIRROR the run-mode layout — chrome strip height + the browser glass panel's
# margin/padding/titlebar on the left, the console column on the right — and are
# tuned by eye against the real window (the overlay shows the white browser_body
# wherever they're off). LEFT/TOP measured from the client top-left; RIGHT/BOTTOM
# are insets from the right/bottom client edges. Scaled by the window DPI at use.
_OVL_LEFT = 36
_OVL_TOP = 129
_OVL_RIGHT = 470
_OVL_BOTTOM = 44
# 1×1 transparent PNG — the live-browser image's initial/blank source (Flet's
# ft.Image needs a valid src; this never actually shows because the panel keeps
# the placeholder mounted until the first real frame arrives).
_BLANK_IMG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
_RING_TRACK = ft.Colors.with_opacity(0.14, "#2b2b2b")
_LINEAR_TRACK = ft.Colors.with_opacity(0.16, "#2b2b2b")
_NEUTRAL_RING = "#c4c4c4"  # calm full ring for the 'action required' state (no color clash)


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
        self._grid_dialog = None
        self._logs_has_content = False
        self._running = False
        # True between a warning ('action required') finish and the next run —
        # lets set_running(False) keep the amber action button instead of resetting
        # it to brand-red (it runs right after the warning status emit).
        self._action_required = False
        self._on_run: Optional[Callable] = None
        self._on_stop: Optional[Callable] = None
        # Terminal output arrives from worker/chromedriver threads; queue it and
        # drain on the UI loop in batches (decoupled = no loop flooding/freeze).
        # Each item is (text, level) where level is a debug-channel severity.
        self._feed_q: "queue.Queue[tuple[str, str]]" = queue.Queue()
        # Plain-text mirror of the rendered feed lines — backs copy-all / save /
        # clear so they don't have to read back ft.Text controls. Capped alongside.
        self._feed_lines: list[str] = []
        # Embedded live browser (issue #19, owned-overlay): the REAL Chrome window
        # is pinned over the panel rectangle as an owned overlay. The overlay is
        # created when the worker reports Chrome is up (attach_browser) and torn
        # down at run end. _overlay_host_hwnd caches our own window handle.
        self._overlay = None
        self._overlay_host_hwnd = None
        self._overlay_suppressed_flag = False
        # True between a TYPE 2 'action required' finish and the operator closing
        # the browser from the panel — Chrome stays embedded (chromedriver is gone
        # but the window lives) so the manual step is finished inside the app.
        self._browser_handoff = False
        self.browser_close_btn = None  # built with the browser panel
        # Per-monitor-DPI-aware so our Win32 geometry matches Flutter's pixels.
        set_process_dpi_aware()

        self._build_page()
        self._build_controls()
        self._render()

    def _build_page(self) -> None:
        self.page.title = APP_WINDOW_TITLE
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
        # Save the manual-entry draft when the OS closes the window (Alt+F4 /
        # taskbar). The grid dialog already saves on close — the path back to a
        # closable window — so this is the belt-and-suspenders catch (issue #18).
        try:
            self.page.window.on_event = self._on_window_event
        except Exception:  # pragma: no cover - older/newer Flet window API
            pass
        apply_theme(self.page)

    def _on_window_event(self, e) -> None:
        if getattr(e, "type", None) == ft.WindowEventType.CLOSE:
            self.save_draft()
            self._kill_browser_on_close()

    def _kill_browser_on_close(self) -> None:
        """On app close (X / Alt+F4), make sure the embedded Chrome doesn't survive
        as a stray taskbar window: an owned window can outlive a cross-process
        owner under detach=True. Kill the tracked browser's process tree and any
        chromedriver. Fast (no process enumeration) and best-effort; the startup
        sweep is the backstop for anything missed."""
        try:
            pid = window_pid(self._overlay.chrome_hwnd) if self._overlay else None
            if pid:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               capture_output=True, check=False)
        except Exception:
            pass
        try:
            subprocess.run(["taskkill", "/F", "/IM", "chromedriver.exe"],
                           capture_output=True, check=False)
        except Exception:
            pass

    def _build_controls(self) -> None:
        # File picker is still needed for importing an Excel file into the grid
        # and for saving the activity-feed log — not for a main-screen file mode.
        self.file_picker = ft.FilePicker()
        self.clipboard = ft.Clipboard()  # system clipboard for "copy all" in the feed
        self.page.services.append(self.file_picker)
        self.page.services.append(self.clipboard)

        # --- Hero: a circular action button wrapped by a progress ring ----------
        self.progress_ring = ft.ProgressRing(
            value=0, width=160, height=160, stroke_width=8,
            color=Color.BRAND, bgcolor=_RING_TRACK,
        )
        # Two distinct glyphs swapped via Container.content — changing a single
        # ft.Icon.name alone does NOT re-render in Flet 0.84 (icon name caching),
        # so we swap the whole content instead (always re-renders).
        self.play_icon = ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, size=50, color=Color.TEXT_ON_BRAND)
        # Dark variant for the amber 'action required' button (white-on-amber has
        # poor contrast — the glyph must be dark on the amber fill).
        self.play_icon_dark = ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, size=50, color=Color.TEXT_PRIMARY)
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
        # Non-chromatic 'action required' signal (color-blind safe), shown beside
        # the hero title only in the warning end state — industry guidance is to
        # pair a status color with a shape/icon, never rely on color alone.
        self.hero_icon = ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, size=24, color=Color.ACTION_REQUIRED, visible=False)
        self._hero_row = ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=Space.SM, tight=True,
            controls=[self.hero_icon, self.hero_value],
        )
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
        # Persistent end-of-run summary card (TYPE 3) — hidden until a run finishes.
        self._summary_holder = self._build_summary_card()

        # --- Process-type inline selector ---------------------------------------
        self._type_segments: dict[str, ft.Container] = {}
        self._type_value = str(parm.TYPE) if parm.TYPE is not None else ""

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
                    ft.Text("פתח את הטבלה, הזן נתונים ולחץ על כפתור ההפעלה", color="#9a9a9a", size=Type.CAPTION[0]),
                ],
            ),
        )
        self.logs_holder = ft.Container(expand=True, content=self.logs_empty_view)

        # --- Embedded live browser (issue #19, owned-overlay) -------------------
        # The white panel area below; the REAL Chrome window is pinned over it as
        # an owned overlay (win_window.BrowserOverlay) while a run is in flight, so
        # this placeholder is only visible in the brief moment before Chrome shows.
        self.browser_placeholder = ft.Container(
            alignment=ft.Alignment.CENTER, expand=True,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER, spacing=Space.MD,
                controls=[
                    ft.ProgressRing(width=34, height=34, stroke_width=4, color=Color.BRAND),
                    ft.Text("ממתין לדפדפן…", color=Color.TEXT_SECONDARY, weight=ft.FontWeight.W_600),
                    ft.Text("הדפדפן יופיע כאן ברגע שהריצה תתחיל",
                            color=Color.TEXT_TERTIARY, size=Type.CAPTION[0]),
                ],
            ),
        )
        self.browser_body = ft.Container(
            expand=True, bgcolor="#ffffff", border_radius=Radius.MD,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS, content=self.browser_placeholder,
        )

        # --- Manual-entry grid (issue #16) --------------------------------------
        self.data_grid = DataGridView(
            self.page, on_change=self._on_grid_change, on_import=self._import_grid_clicked,
            on_save=self._close_grid_dialog)
        self._restore_draft()  # repopulate the grid from the last session (issue #18)
        if self._type_value:
            self.data_grid.rebuild_for_type(self._type_value)
        self.manual_badge = ft.Container(
            width=38, height=38, border_radius=Radius.PILL, alignment=ft.Alignment.CENTER,
            bgcolor=Color.BRAND_TINT,
            content=ft.Icon(ft.Icons.TABLE_CHART_OUTLINED, size=20, color=Color.BRAND),
        )
        self.manual_summary_text = ft.Text(
            "אין נתונים", size=Type.BODY[0], color=Color.TEXT_PRIMARY,
            weight=ft.FontWeight.W_600, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True,
        )
        self.manual_sub_text = ft.Text(
            "הזנה ידנית בטבלה", size=Type.CAPTION[0], color=Color.TEXT_TERTIARY,
            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
        )
        self.open_grid_button = ft.TextButton(
            "פתח טבלה", icon=ft.Icons.EDIT_NOTE_ROUNDED,
            style=ft.ButtonStyle(color=Color.BRAND, padding=Space.SM),
            on_click=lambda _: self.show_grid_dialog(),
        )
        # The entry grid is the single input source (epic #14 / #18 — Excel is an
        # import path into it, not a separate mode). Seed the zone once.
        self._input_zone_holder = ft.Container(content=self._build_manual_zone())
        self._refresh_manual_zone()

    # --------------------------------------------------------------- window controls
    def _win_minimize(self, e):
        self.page.window.minimized = True
        self._safe_update()

    def _win_maximize(self, e):
        self.page.window.maximized = not self.page.window.maximized
        self._safe_update()

    async def _win_close(self, e):
        # The app's custom title-bar X. This does NOT fire the OS-level CLOSE
        # window event, so kill the embedded browser here too (issue #19) before
        # closing — otherwise the owned Chrome can outlive the app as a stray
        # taskbar window under detach=True.
        self.save_draft()
        self._kill_browser_on_close()
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
        # The manual-entry grid's columns are derived from TYPE — keep it in sync.
        self.data_grid.rebuild_for_type(key)
        self._refresh_manual_zone()
        label = _TYPE_META.get(key, ("", None))[0]
        self.status_text.value = f"מצב: {label}"
        self.status_text.color = Color.TEXT_SECONDARY
        self.hero_value.value, self.hero_value.color = "מוכן", Color.TEXT_PRIMARY
        self.hero_icon.visible = False
        # Clear any stranded 'action required' styling when switching process type.
        if self._action_required:
            self._action_required = False
            self.action_circle.bgcolor = Color.BRAND
            self.action_circle.shadow.color = ft.Colors.with_opacity(0.35, Color.BRAND)
            self.action_circle.content = self.play_icon
            self.progress_ring.color = self.linear.color = Color.BRAND
            self.progress_ring.value = self.linear.value = 0
        self._safe_update()

    def _refresh_type(self) -> None:
        """Re-sync the selector after the settings dialog may have changed TYPE."""
        self._type_value = str(parm.TYPE) if parm.TYPE is not None else ""
        self._style_type_segments()
        # The grid columns are derived from TYPE — keep it in sync.
        self.data_grid.rebuild_for_type(self._type_value)
        self._refresh_manual_zone()

    # ------------------------------------------------------------------ manual zone
    def _build_manual_zone(self) -> ft.Container:
        return ft.Container(
            bgcolor=_GLASS_CHIP, border_radius=Radius.LG,
            border=ft.border.all(1, ft.Colors.with_opacity(0.5, "#ffffff")),
            padding=ft.padding.symmetric(horizontal=Space.MD, vertical=Space.SM),
            content=ft.Row(
                spacing=Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    self.manual_badge,
                    ft.Column(
                        spacing=0, expand=True, tight=True,
                        controls=[self.manual_summary_text, self.manual_sub_text],
                    ),
                    self.open_grid_button,
                ],
            ),
        )

    def _refresh_manual_zone(self) -> None:
        """Mirror the grid's state into the manual-zone chip (summary + badge)."""
        empty = self.data_grid.is_empty()
        valid = self.data_grid.is_valid()
        self.manual_summary_text.value = self.data_grid.summary()
        if empty:
            self.manual_sub_text.value = "הזנה ידנית בטבלה"
            self.manual_sub_text.color = Color.TEXT_TERTIARY
            self.manual_badge.bgcolor = Color.BRAND_TINT
            self.manual_badge.content.name = ft.Icons.TABLE_CHART_OUTLINED
            self.manual_badge.content.color = Color.BRAND
        elif valid:
            self.manual_sub_text.value = "מוכן להרצה"
            self.manual_sub_text.color = Color.SUCCESS
            self.manual_badge.bgcolor = ft.Colors.with_opacity(0.18, Color.SUCCESS)
            self.manual_badge.content.name = ft.Icons.TASK_ALT_ROUNDED
            self.manual_badge.content.color = Color.SUCCESS
        else:
            self.manual_sub_text.value = "יש לתקן שורות פגומות"
            self.manual_sub_text.color = Color.WARNING
            self.manual_badge.bgcolor = ft.Colors.with_opacity(0.18, Color.WARNING)
            self.manual_badge.content.name = ft.Icons.WARNING_AMBER_ROUNDED
            self.manual_badge.content.color = Color.WARNING

    def _on_grid_change(self) -> None:
        # Called from the grid on every edit. While the grid dialog is open the
        # chip is hidden behind it, so DON'T run a full page.update() here: doing
        # it on each keystroke rebuilds the focused TextField and drops the
        # cursor (the user has to click back in after every character). The chip
        # is refreshed when the dialog closes (_close_grid_dialog/_on_dismissed).
        if self._grid_dialog is not None:
            return
        self._refresh_manual_zone()
        self._safe_update()

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
                            self._hero_row,
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

    async def _flash_btn(self, btn, icon, color, tip, rest_icon, rest_tip, rest_color=Term.TITLE) -> None:
        """Briefly swap a toolbar icon to confirm an action (no popup alert)."""
        if btn is None:
            return
        btn.icon, btn.icon_color, btn.tooltip = icon, color, tip
        self._safe_update()
        await asyncio.sleep(1.4)
        # The dialog may have closed/reopened (new button) meanwhile — only restore ours.
        if btn.icon == icon:
            btn.icon, btn.icon_color, btn.tooltip = rest_icon, rest_color, rest_tip
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
                    self._input_zone_holder,
                    self._build_hero(),
                    self.linear,
                    self._summary_holder,
                ],
            ),
        )

    # ------------------------------------------------------------ browser preview
    def _build_browser_panel(self) -> ft.Container:
        """The embedded live-browser panel (issue #19).

        Same glass treatment as the console panel, with a slim title bar carrying
        a 'live' indicator and the mirrored Chrome image below. Built hidden; it
        is revealed beside the console only while a run is in flight (see
        _apply_run_layout), filling the empty background space the console leaves.
        """
        # The bottom margin is an optical correction: the LIVE label is all-caps,
        # so its glyphs sit in the upper part of the text box (the descender space
        # below goes unused) — a box-centred dot looks low. Nudging it up ~1px
        # centres it on the letters themselves.
        live_dot = ft.Container(width=9, height=9, border_radius=Radius.PILL, bgcolor=Color.BRAND,
                                margin=ft.margin.only(bottom=2))
        # Revealed only during a TYPE 2 'action required' handoff — closes the
        # embedded browser once the operator finished the manual step. Filled in
        # the brand color so the one next action is unmissable.
        self.browser_close_btn = ft.FilledButton(
            "סיימתי — סגור דפדפן", icon=ft.Icons.CHECK_ROUNDED, visible=False,
            style=ft.ButtonStyle(
                bgcolor=Color.BRAND, color="#ffffff",
                padding=ft.padding.symmetric(horizontal=Space.LG, vertical=Space.SM),
            ),
            on_click=self._close_handoff_browser,
        )
        # Keep the dot + LIVE label in their own tight group so the dot centres
        # against the label height alone — not the taller 'close browser' button,
        # which would otherwise stretch the row and drop the dot below the text.
        live_group = ft.Row(
            spacing=Space.XS, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                live_dot,
                ft.Text("LIVE", size=Type.CAPTION[0], weight=ft.FontWeight.W_700, color=Color.BRAND),
            ],
        )
        titlebar = ft.Row(
            spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.PUBLIC_ROUNDED, size=18, color=Color.TEXT_SECONDARY),
                ft.Text("דפדפן חי", size=Type.TITLE[0], weight=ft.FontWeight.W_700, color=Color.TEXT_PRIMARY),
                ft.Container(expand=True),
                self.browser_close_btn,
                live_group,
            ],
        )
        return ft.Container(
            visible=False, expand=True,
            margin=ft.margin.only(top=Space.XS, bottom=Space.XXL, left=Space.LG),
            bgcolor=_GLASS_PANEL, border=ft.border.all(1, ft.Colors.with_opacity(0.55, "#ffffff")),
            border_radius=24, shadow=_PANEL_SHADOW, padding=Space.XL,
            content=ft.Column(
                spacing=Space.MD, expand=True,
                controls=[
                    titlebar,
                    ft.Divider(color=ft.Colors.with_opacity(0.5, Color.BORDER), height=1),
                    self.browser_body,
                ],
            ),
        )

    # ------------------------------------------------------ embedded browser overlay
    def attach_browser(self, hwnd: int) -> None:
        """Embed the live Chrome window (its OS handle) as an owned overlay pinned
        over the browser panel (issue #19). Called once the worker reports Chrome
        is up. Best-effort: if the host window or the embed fails, the run just
        proceeds without the live panel."""
        if not hwnd:
            return
        self._stop_browser_overlay()  # guard against a stale overlay
        host = find_window_by_title(self.page.title)
        if not host:
            return
        self._overlay_host_hwnd = host
        overlay = BrowserOverlay(hwnd, host, self._browser_rect_provider)
        if overlay.start():
            self._overlay = overlay

    def enter_browser_handoff(self) -> None:
        """TYPE 2 'action required' finish: keep Chrome EMBEDDED in the panel so
        the operator finishes the manual step right here (the overlay is fully
        interactive), and reveal a close button to shut the browser when done.
        chromedriver is already gone; only the window lives on."""
        if self._overlay is None:
            return
        self._browser_handoff = True
        if self.browser_close_btn is not None:
            self.browser_close_btn.visible = True
        self._safe_update()

    def _close_handoff_browser(self, _e=None) -> None:
        """Panel close button: shut the handoff Chrome, fold the panel away, and
        return the main action button to its idle 'waiting' state."""
        overlay, self._overlay = self._overlay, None
        self._browser_handoff = False
        if self.browser_close_btn is not None:
            self.browser_close_btn.visible = False
        if overlay is not None:
            overlay.stop()
            close_window(overlay.chrome_hwnd)
        # The whole operation is over → return the WHOLE screen to its clean idle
        # state, not just the button: drop the 'action required' status text, the
        # warning glyph, the amber progress bar and the counter — a fresh 'ready'
        # screen. (Mirrors the idle reset in the process-type switch handler.)
        self._action_required = False
        label = _TYPE_META.get(self._type_value, ("", None))[0]
        self.status_text.value = f"מצב: {label}" if label else "מוכן"
        self.status_text.color = Color.TEXT_SECONDARY
        self.hero_value.value, self.hero_value.color = "מוכן", Color.TEXT_PRIMARY
        self.hero_icon.visible = False
        self.progress_ring.color = self.linear.color = Color.BRAND
        self.progress_ring.value = self.linear.value = 0
        self.counter_text.value = ""
        self.status_dot.bgcolor = Color.TEXT_TERTIARY
        # set_running(False) re-renders the button to the idle ▶, folds the panel,
        # and unlocks edits.
        self.set_running(False)

    def _stop_browser_overlay(self) -> None:
        """Stop tracking the overlay (Chrome is about to be closed by the driver)."""
        if self._overlay is not None:
            self._overlay.stop()
            self._overlay = None

    def _browser_rect_provider(self):
        """Target screen rectangle (physical px) for the overlay, or None to hide
        it (idle, a covering dialog is open, or the window is minimized). Computed
        from the live window geometry and the layout insets (see _OVL_*)."""
        if (not self._running and not self._browser_handoff) or self._overlay_suppressed_flag:
            return None
        host = self._overlay_host_hwnd
        if not host:
            return None
        m = host_metrics(host)
        if m is None:
            return None
        ox, oy, cw, ch, s = m
        x = ox + int(_OVL_LEFT * s)
        y = oy + int(_OVL_TOP * s)
        right = ox + cw - int(_OVL_RIGHT * s)
        bottom = oy + ch - int(_OVL_BOTTOM * s)
        w, h = right - x, bottom - y
        if w <= 0 or h <= 0:
            return None
        return (x, y, w, h)

    def set_overlay_suppressed(self, suppressed: bool) -> None:
        """Temporarily hide the overlay (e.g. while a modal dialog covers the
        panel — the owned window can't be clipped, so it would paint over it)."""
        self._overlay_suppressed_flag = suppressed

    def reset_browser(self) -> None:
        """Return the panel body to its 'waiting' placeholder."""
        self.browser_body.content = self.browser_placeholder

    def _apply_run_layout(self, running: bool) -> None:
        """Show/hide the live-browser panel beside the console (issue #19).

        While running, the console panel keeps its fixed width on the RTL leading
        (right) side and the browser panel fills the remaining space to its left
        (the real Chrome window is pinned over it as an owned overlay); idle, the
        console returns to the centre and the overlay is torn down."""
        row = getattr(self, "_console_row", None)
        if running:
            # A new run while a handoff browser is still embedded: close it —
            # the new run brings its own Chrome into the panel.
            if self._browser_handoff:
                self._browser_handoff = False
                if self.browser_close_btn is not None:
                    self.browser_close_btn.visible = False
                overlay, self._overlay = self._overlay, None
                if overlay is not None:
                    overlay.stop()
                    close_window(overlay.chrome_hwnd)
            self.reset_browser()
            self._browser_panel.visible = True
            if row is not None:
                if self._browser_panel not in row.controls:
                    row.controls.append(self._browser_panel)
                row.alignment = ft.MainAxisAlignment.START
        else:
            # During a TYPE 2 handoff the run is over but the operator is still
            # finishing the manual step inside the embedded browser — keep the
            # panel (and the overlay) up; _close_handoff_browser folds it later.
            if self._browser_handoff:
                return
            self._stop_browser_overlay()
            self._browser_panel.visible = False
            self.reset_browser()
            if row is not None:
                if self._browser_panel in row.controls:
                    row.controls.remove(self._browser_panel)
                row.alignment = ft.MainAxisAlignment.CENTER

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
        # The live-browser panel (issue #19) is built once and joins the row only
        # while a run is in flight (see _apply_run_layout).
        self._browser_panel = self._build_browser_panel()
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

    def bind_actions(self, on_run, on_stop, on_settings, on_help) -> None:
        self._on_run = on_run
        self._on_stop = on_stop
        self.settings_button.on_click = on_settings
        self.help_button.on_click = on_help

    def _build_summary_card(self) -> ft.Container:
        """Persistent end-of-run summary (TYPE 3). Shows the session count and,
        when present, the full list of ID numbers that weren't updated — visible
        and selectable so the operator can copy them, instead of being truncated
        on the one-line status field."""
        self._summary_success_text = ft.Text(
            "", size=Type.BODY[0], color=Color.TEXT_PRIMARY, weight=ft.FontWeight.W_500,
        )
        self._summary_warn_title = ft.Text(
            "", size=Type.CAPTION[0], color=Color.ACTION_REQUIRED, weight=ft.FontWeight.W_700,
        )
        # Selectable too, but the copy button is the primary affordance — it copies
        # the clean IDs (no LTR-isolate chars), one per line for easy re-checking.
        self._summary_ids_text = ft.Text(
            "", size=Type.CAPTION[0], color=Color.TEXT_PRIMARY, selectable=True,
        )
        self._summary_ids_raw: list[str] = []
        self._summary_copy_btn = ft.IconButton(
            icon=ft.Icons.CONTENT_COPY_ROUNDED, icon_size=16, icon_color=Color.TEXT_SECONDARY,
            tooltip="העתק ת.ז.", on_click=lambda _: self._copy_missing_ids(),
        )
        self._summary_warn_block = ft.Container(
            visible=False,
            bgcolor=ft.Colors.with_opacity(0.12, Color.ACTION_REQUIRED),
            border_radius=Radius.MD, padding=Space.SM,
            content=ft.Column(spacing=Space.XS, controls=[
                ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
                    ft.Row(spacing=Space.SM, controls=[
                        ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, size=18, color=Color.ACTION_REQUIRED),
                        self._summary_warn_title,
                    ]),
                    self._summary_copy_btn,
                ]),
                ft.Container(
                    height=120,
                    content=ft.Column(scroll=ft.ScrollMode.AUTO, controls=[self._summary_ids_text]),
                ),
            ]),
        )
        header = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Row(spacing=Space.SM, controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, size=20, color=Color.SUCCESS),
                    ft.Text("סיכום ריצה", size=Type.TITLE[0], weight=ft.FontWeight.W_700,
                            color=Color.TEXT_PRIMARY),
                ]),
                ft.IconButton(
                    icon=ft.Icons.CLOSE_ROUNDED, icon_size=18, icon_color=Color.TEXT_SECONDARY,
                    tooltip="סגור", on_click=lambda _: self.clear_run_summary(),
                ),
            ],
        )
        return ft.Container(
            visible=False, width=_PANEL_WIDTH - 2 * Space.XL,
            bgcolor=Color.SURFACE, border_radius=Radius.LG,
            border=ft.border.all(1, ft.Colors.with_opacity(0.5, Color.BORDER)),
            padding=Space.MD,
            content=ft.Column(spacing=Space.SM, controls=[
                header, self._summary_success_text, self._summary_warn_block,
            ]),
        )

    def show_run_summary(self, summary: dict | None) -> None:
        """Populate and reveal the run-summary card from a processor result dict."""
        if not summary:
            return
        sessions = summary.get("sessions_created", 0)
        missing = summary.get("missing_ids") or []
        self._summary_success_text.value = f"{ltr_isolate(sessions)} מפגשים נוצרו ודווחו בהצלחה"
        if missing:
            self._summary_ids_raw = [str(x) for x in missing]
            self._summary_warn_title.value = f"{ltr_isolate(len(missing))} ת.ז. לא אותרו ולא עודכנו:"
            self._summary_ids_text.value = ", ".join(ltr_isolate(x) for x in missing)
            self._summary_warn_block.visible = True
        else:
            self._summary_ids_raw = []
            self._summary_warn_block.visible = False
        self._summary_holder.visible = True
        self._safe_update()

    def clear_run_summary(self) -> None:
        self._summary_holder.visible = False
        self._safe_update()

    def _copy_missing_ids(self) -> None:
        """Copy the unmatched IDs (clean, no isolate chars) — one per line."""
        if not self._summary_ids_raw:
            return
        self.page.run_task(self._copy_missing_ids_async)

    async def _copy_missing_ids_async(self) -> None:
        try:
            await self.clipboard.set("\n".join(self._summary_ids_raw))
        except Exception:
            return
        await self._flash_btn(
            self._summary_copy_btn, ft.Icons.CHECK_ROUNDED, Color.SUCCESS, "הועתק!",
            ft.Icons.CONTENT_COPY_ROUNDED, "העתק ת.ז.", rest_color=Color.TEXT_SECONDARY,
        )

    def set_status(self, text: str, level: str | None = None) -> None:
        """Updates the hero state/caption only. The feed shows real terminal output."""
        if not text:
            return
        self.status_text.value = text
        # The 'action required' glyph belongs to the warning state only; clear it
        # by default so any other status update drops it. The warning branch below
        # turns it back on. (set_running(False) deliberately leaves it untouched so
        # it survives the finish that follows a warning emit.)
        self.hero_icon.visible = False
        self._action_required = False  # warning branch re-arms it
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
            # 'Action required' (TYPE 2 end state). The amber lives on the action
            # button itself (with a dark glyph for contrast); the ring goes calm
            # neutral grey and the text clean near-black, so nothing clashes. A
            # small amber warning glyph sits beside the title, and the progress bar
            # echoes the amber. The button color is (re)applied by set_running's
            # idle branch via _action_required, since that runs after this on finish.
            self._action_required = True
            self.status_text.color = self.hero_value.color = Color.TEXT_PRIMARY
            self.progress_ring.color = _NEUTRAL_RING
            self.linear.color = Color.ACTION_REQUIRED
            self.progress_ring.value = self.linear.value = 1
            self.action_circle.bgcolor = Color.ACTION_REQUIRED
            self.action_circle.shadow.color = ft.Colors.with_opacity(0.35, Color.ACTION_REQUIRED)
            self.action_circle.content = self.play_icon_dark
            self.hero_icon.visible = True
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
            self.counter_text.value = f"{ltr_isolate(current or 0)} מתוך {ltr_isolate(total)} רשומות"
        if self._running:
            self.hero_value.value = f"{int(clamped * 100)}%"
            self.hero_value.color = Color.TEXT_PRIMARY
            self.hero_icon.visible = False  # only the warning end state shows it
        self._safe_update()

    def set_running(self, is_running: bool) -> None:
        self._running = is_running
        # Reveal/hide the embedded live-browser panel beside the console (#19).
        self._apply_run_layout(is_running)
        self.action_circle.disabled = False  # re-enable after a stop/finish cycle
        # Draw the eye to the feed button while output is streaming.
        self.feed_button.icon_color = Color.BRAND if is_running else Color.TEXT_SECONDARY
        if is_running:
            self.hero_icon.visible = False  # clear any prior 'action required' glyph
            self._action_required = False
            # One red for every button state: the running/stop affordance stays in
            # BRAND and the state change is carried by the icon (▶→⏹) + the spinning
            # progress ring. DANGER is reserved for genuine errors/destructive
            # actions so red keeps its meaning (see the theme decision).
            self.action_circle.bgcolor = Color.BRAND
            self.action_circle.shadow.color = ft.Colors.with_opacity(0.35, Color.BRAND)
            self.action_circle.content = self.stop_icon  # square while running
            self.action_circle.tooltip = "עצור תהליך"
            self.progress_ring.color = self.linear.color = Color.BRAND
            self.progress_ring.value = self.linear.value = 0
            self.status_dot.bgcolor = Color.BRAND
            self.hero_value.value, self.hero_value.color = "0%", Color.TEXT_PRIMARY
            self.counter_text.value = ""
            self._summary_holder.visible = False  # drop the previous run's summary
            # Dim the type selector — switching process mid-run is blocked.
            for seg in self._type_segments.values():
                seg.opacity = 0.55 if seg.data != self._type_value else 1.0
        elif self._action_required:
            # Finished in an 'action required' state — keep the amber button with
            # its dark glyph (set by the warning branch) instead of resetting to
            # brand-red. This runs right after the warning status emit on finish.
            self.action_circle.bgcolor = Color.ACTION_REQUIRED
            self.action_circle.shadow.color = ft.Colors.with_opacity(0.35, Color.ACTION_REQUIRED)
            self.action_circle.content = self.play_icon_dark
            self.action_circle.tooltip = "הפעל תהליך"
            self.status_dot.bgcolor = Color.TEXT_TERTIARY
            for seg in self._type_segments.values():
                seg.opacity = 1.0
        else:
            self.action_circle.bgcolor = Color.BRAND
            self.action_circle.shadow.color = ft.Colors.with_opacity(0.35, Color.BRAND)
            self.action_circle.content = self.play_icon  # triangle when idle
            self.action_circle.tooltip = "הפעל תהליך"
            self.status_dot.bgcolor = Color.TEXT_TERTIARY
            for seg in self._type_segments.values():
                seg.opacity = 1.0
        # Lock the data-entry table and settings while a run is in flight — editing
        # the input mid-run would desync what's being processed from what's shown.
        # Both are reachable only via these two buttons (the dialogs themselves are
        # guarded too), so disabling them seals every edit path. State is restored
        # symmetrically when the run finishes/stops (set_running(False)).
        self._set_edit_locked(is_running)
        self._safe_update()

    def _set_edit_locked(self, locked: bool) -> None:
        """Enable/disable the entry-grid and settings entry points as one unit."""
        self.open_grid_button.disabled = locked
        self.open_grid_button.opacity = 0.5 if locked else 1.0
        self.open_grid_button.tooltip = "לא ניתן לערוך את הטבלה בזמן ריצה" if locked else None
        self.settings_button.disabled = locked
        self.settings_button.opacity = 0.5 if locked else 1.0
        self.settings_button.tooltip = "לא ניתן לשנות הגדרות בזמן ריצה" if locked else "הגדרות"

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

    # ------------------------------------------------------------- manual grid
    def show_grid_dialog(self) -> None:
        """Open the manual-entry table as a modal editor (issue #16)."""
        if self._running:
            return  # input is locked while a run is in flight
        if self._grid_dialog is not None:
            return
        close_btn = ft.IconButton(
            ft.Icons.CLOSE_ROUNDED, icon_color=Color.TEXT_SECONDARY, icon_size=20,
            tooltip="סגור", on_click=lambda _: self._close_grid_dialog(),
        )
        # "ייבא מ-Excel" and "שמור וסגור" now live in the grid's own toolbar
        # (next to add/paste/clear), so every action sits on one row — see
        # DataGridView. The host still owns their handlers via the on_import /
        # on_save callbacks passed when the grid was constructed.
        self._grid_dialog = ft.AlertDialog(
            modal=True, rtl=True,
            # Same translucent glass as the settings dialog. The main panel is
            # hidden below so only the background sits behind the glass — without
            # that, the panel's own glass shows through and washes the dialog out.
            bgcolor=ft.Colors.with_opacity(0.62, "#ffffff"),
            barrier_color=ft.Colors.with_opacity(0.06, "#000000"),
            shape=ft.RoundedRectangleBorder(radius=Radius.LG),
            content_padding=0,
            on_dismiss=lambda _: self._on_grid_dismissed(),
            content=ft.Container(
                width=980, height=620, rtl=True,
                border=ft.border.all(1, ft.Colors.with_opacity(0.6, "#ffffff")),
                border_radius=Radius.LG,
                content=ft.Column(spacing=0, controls=[
                    ft.Container(
                        padding=ft.padding.only(top=Space.SM, left=Space.SM, right=Space.SM),
                        content=ft.Row([close_btn], alignment=ft.MainAxisAlignment.END),
                    ),
                    ft.Container(expand=True, content=self.data_grid.build_surface()),
                ]),
            ),
        )
        # Hide the main panel so only the background shows behind the glass dialog.
        if getattr(self, "_console_row", None) is not None:
            self._console_row.visible = False
        self.page.show_dialog(self._grid_dialog)
        self._safe_update()

    def _close_grid_dialog(self) -> None:
        if self._grid_dialog is not None:
            self._grid_dialog.open = False
            self.page.pop_dialog()
            self._grid_dialog = None
        # Restore the main panel that was hidden while the grid was open.
        if getattr(self, "_console_row", None) is not None:
            self._console_row.visible = True
        self.data_grid.detach()
        self.save_draft()  # persist the table the user just edited (issue #18)
        self._refresh_manual_zone()
        self._safe_update()

    def _on_grid_dismissed(self) -> None:
        self._grid_dialog = None
        if getattr(self, "_console_row", None) is not None:
            self._console_row.visible = True
        self.data_grid.detach()
        self.save_draft()  # Esc/barrier dismissal still saves (issue #18)
        self._refresh_manual_zone()
        self._safe_update()

    # ----------------------------------------------------------- draft (issue #18)
    def _restore_draft(self) -> None:
        """Repopulate the grid from the last session's draft, if any. Silent —
        a missing/corrupt draft must never block startup."""
        try:
            from src.core.draft_store import load_draft
            state = load_draft()
            if state:
                self.data_grid.restore_state(state)
        except Exception:
            pass

    def save_draft(self) -> None:
        """Snapshot the grid to disk so a half-typed table survives a restart."""
        try:
            from src.core.draft_store import save_draft as _persist
            _persist(self.data_grid.export_state())
        except Exception:
            pass

    def get_manual_source(self):
        """Resolve the manual grid into a data source, or None (with an alert)."""
        if self.data_grid.is_empty():
            self.show_alert("אין נתונים", Status.MANUAL_EMPTY, "warning")
            return None
        reasons = self.data_grid.invalid_reasons()
        if reasons:
            self.show_alert("שורות פגומות", Status.MANUAL_INVALID + "\n\n• " + "\n• ".join(reasons), "warning")
            return None
        return self.data_grid.to_source()

    # --------------------------------------------------- grid Excel import/export
    def _import_grid_clicked(self) -> None:
        self.page.run_task(self._import_grid_async)

    async def _import_grid_async(self) -> None:
        files = await self.file_picker.pick_files(
            allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx", "xls"], dialog_title="ייבא קובץ Excel לטבלה",
        )
        if not files:
            return
        path = files[0].path or files[0].name
        try:
            if self._type_value == "3":
                from src.automation.excel_import import read_matrix
                self.data_grid.import_matrix(read_matrix(path))
            else:
                from src.automation.excel_import import read_tabular
                self.data_grid.import_tabular_rows(read_tabular(path, self._type_value))
        except Exception as ex:  # malformed/locked file — surface on the grid note
            self.data_grid.note(f"ייבוא נכשל: {ex}", "error")
            return
        self.save_draft()  # the imported rows are now part of the draft

    # ------------------------------------------------------------- settings modal
    def show_settings_view(self, settings_container) -> None:
        if self._running:
            return  # settings are locked while a run is in flight
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
            # Fixed-width content so the dialog keeps a constant size regardless of
            # message length — short messages no longer collapse to a narrow box and
            # long ones wrap inside the same width instead of stretching the dialog.
            content=ft.Container(
                width=420,
                content=ft.Text(message, selectable=True, color=Color.TEXT_PRIMARY, text_align=ft.TextAlign.RIGHT),
            ),
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
