import threading

from src.core.config import config_instance as parm
from src.core.constants import T3_MODE_COMPARE, T3_MODE_UPSERT
from src.core.paths import is_frozen
from src.core.status_messages import Status
from src.core.version import __version__
from src.core.utils import strip_isolates
from src.ui.settings_controller import SettingsController
from src.ui.worker_manager import WorkerManager


class Controller:
    """
    Main application controller. Acts as a thin coordinator that delegates to:
    - SettingsController: settings dialog management
    - WorkerManager: worker lifecycle
    """

    def __init__(self, page, main_view):
        self.page = page
        self.main_view = main_view

        self.settings_controller = SettingsController(page, main_view)
        self.worker_manager = WorkerManager(main_view)

        self._attach_events()

        # State tracking for progress
        self.total_items = 0
        self.current_item = 0
        # TYPE 2 handoff: the still-alive driver (chromedriver + embedded Chrome)
        # left running so the operator finishes a manual step. Held here so it
        # survives the worker's end and is closed cleanly on "done" / next run.
        self._handoff_dm = None

        # Update state surfaced in the settings panel (no launch popup anymore).
        # A frozen build checks in the background on launch; a source checkout has
        # no installer to update to, so it just reports "source". Visible to every
        # install — the settings panel distinguishes up-to-date from "couldn't
        # check" (and then hints at SSH).
        self._update_info = {"state": "checking"} if is_frozen() else {"state": "source"}
        self._update_controls = None  # the settings update-section refs, while open
        if is_frozen():
            self._start_update_check()

    def _start_update_check(self):
        """Check for a newer build on a daemon thread (a slow/blocked network
        must never delay startup) and refresh the settings panel if it's open.
        The result is stashed on ``self._update_info`` so opening settings later
        renders it without re-checking."""
        def _run():
            self._update_info = self._fetch_update_info()
            if self.page:
                self.page.run_task(self._safe_render_update_section)
        threading.Thread(target=_run, daemon=True).start()

    def _fetch_update_info(self) -> dict:
        """Return the channel-appropriate status dict (state available/current/
        error). Channel = SSH/VPS mirror when the SSH mirror is *configured*
        (SSH_REMOTE + SSH_KEY_PATH in config.ini), else GitHub. We key off the
        config fields, not the session DEV_MODE flag: DEV_MODE resets to False
        on every launch (config.py), so it would always pick GitHub at startup —
        but the gov machine that needs the VPS channel is exactly the one with
        the SSH mirror persisted."""
        if parm.SSH_REMOTE and parm.SSH_KEY_PATH:
            from src.core.update_checker import check_for_update_ssh
            return check_for_update_ssh(parm.SSH_REMOTE, parm.SSH_KEY_PATH)
        from src.core.update_checker import check_for_update
        return check_for_update()

    # ----------------------------------------------------------- settings panel
    def build_update_section(self):
        """Build the 'אודות ועדכונים' control for the settings dialog (fresh refs
        each open) and render the current status into it. Returns the control."""
        import flet as ft
        from src.ui.theme import Color, Space, Type

        self._upd_icon = ft.Icon(ft.Icons.INFO_OUTLINE_ROUNDED, color=Color.TEXT_SECONDARY, size=18)
        self._upd_ring = ft.ProgressRing(width=16, height=16, stroke_width=2, color=Color.BRAND, visible=False)
        self._upd_text = ft.Text("", color=Color.TEXT_SECONDARY, size=Type.BODY[0], expand=True)
        self._upd_button = ft.TextButton("בדוק עכשיו", on_click=lambda _: self._on_check_now())
        installed = ft.Text(f"גרסה מותקנת: {__version__}", color=Color.TEXT_SECONDARY, size=Type.CAPTION[0])
        status_row = ft.Row(
            spacing=Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self._upd_icon, self._upd_ring, self._upd_text, self._upd_button],
        )
        self._update_controls = (self._upd_icon, self._upd_ring, self._upd_text, self._upd_button)
        self._render_update_section()
        return ft.Column(spacing=Space.XS, controls=[installed, status_row])

    def _render_update_section(self):
        """Paint the update controls from ``self._update_info``. Best-effort —
        mutating an unmounted control (settings closed) just raises and is
        swallowed; the next open rebuilds from the same stashed status."""
        if not self._update_controls:
            return
        import flet as ft
        from src.ui.theme import Color
        st = self._update_info or {"state": "error", "reason": "network"}
        state = st.get("state")
        btn = self._upd_button
        self._upd_ring.visible = state == "checking"

        if state == "available":
            self._upd_icon.name = ft.Icons.SYSTEM_UPDATE_ALT_ROUNDED
            self._upd_icon.color = Color.BRAND
            self._upd_text.value = f"גרסה חדשה זמינה ({st.get('version', '')})"
            self._upd_text.color = Color.TEXT_PRIMARY
            btn.text, btn.visible = "עדכן עכשיו", True
            btn.on_click = lambda _: self.apply_update()
        elif state == "current":
            self._upd_icon.name = ft.Icons.CHECK_CIRCLE_ROUNDED
            self._upd_icon.color = Color.SUCCESS
            self._upd_text.value = "מותקנת הגרסה האחרונה"
            self._upd_text.color = Color.TEXT_SECONDARY
            btn.text, btn.visible = "בדוק עכשיו", True
            btn.on_click = lambda _: self._on_check_now()
        elif state == "checking":
            self._upd_icon.name = ft.Icons.HOURGLASS_EMPTY_ROUNDED
            self._upd_icon.color = Color.TEXT_SECONDARY
            self._upd_text.value = "בודק עדכונים…"
            self._upd_text.color = Color.TEXT_SECONDARY
            btn.visible = False
        elif state == "source":
            self._upd_icon.name = ft.Icons.INFO_OUTLINE_ROUNDED
            self._upd_icon.color = Color.TEXT_SECONDARY
            self._upd_text.value = "הרצה ממקור — ללא עדכון אוטומטי"
            self._upd_text.color = Color.TEXT_SECONDARY
            btn.visible = False
        else:  # error — distinguish a failed SSH pull from "no channel / blocked"
            self._upd_icon.name = ft.Icons.WARNING_AMBER_ROUNDED
            self._upd_icon.color = Color.ACTION_REQUIRED
            if st.get("reason") == "ssh":
                self._upd_text.value = "בדיקת העדכון דרך SSH נכשלה — בדוק כתובת/מפתח וחיבור."
            else:
                self._upd_text.value = "לא ניתן לבדוק עדכונים. אם המחשב מסונן — הפעל 'שיקוף SSH' בהגדרות מתקדמות."
            self._upd_text.color = Color.TEXT_SECONDARY
            btn.text, btn.visible = "בדוק עכשיו", True
            btn.on_click = lambda _: self._on_check_now()

        try:
            for c in self._update_controls:
                c.update()
        except Exception:
            pass  # not mounted (settings closed) — values are set, render on next open

    async def _safe_render_update_section(self):
        self._render_update_section()

    def _on_check_now(self):
        """Manual re-check from the settings panel."""
        self._update_info = {"state": "checking"}
        self._render_update_section()

        def _run():
            self._update_info = self._fetch_update_info()
            if self.page:
                self.page.run_task(self._safe_render_update_section)
        threading.Thread(target=_run, daemon=True).start()

    def apply_update(self):
        """Download + install the available update with a live 'updating' modal,
        then close the app so the per-user installer can replace the locked files.

        Closing settings and showing the modal happen in the same UI tick, so a
        dialog is always on screen — no flash of bare background (the old bug)."""
        info = self._update_info
        if not info or info.get("state") != "available":
            return
        # GitHub release without a .exe asset — nothing to silent-install; point
        # the operator at the release page instead.
        if info.get("channel") == "github" and not info.get("url"):
            self.main_view.show_alert(
                "גרסה חדשה זמינה",
                f"ניתן להוריד את הגרסה האחרונה מ-GitHub:\n{info.get('page', '')}",
                "info",
            )
            return

        self.main_view.switch_to_main()       # close settings cleanly (restores panel)…
        self.main_view.show_updating_modal()  # …then cover it with the modal — no gap

        def _progress(pct):
            if self.page:
                self.page.run_task(self._safe_set_updating, "מוריד עדכון…", pct)

        def _run():
            try:
                if info["channel"] == "ssh":
                    if self.page:  # scp % needs the manifest size; show indeterminate meanwhile
                        self.page.run_task(self._safe_set_updating, "מוריד ומאמת עדכון…", None)
                    from src.core.update_checker import download_and_launch_ssh
                    download_and_launch_ssh(info["remote_exe"], parm.SSH_KEY_PATH,
                                            info["sha256"], info.get("size"), on_progress=_progress)
                else:
                    from src.core.update_checker import download_and_launch
                    download_and_launch(info["url"], on_progress=_progress)
                if self.page:
                    self.page.run_task(self._safe_set_updating, "מפעיל התקנה…", 100)
            except Exception as e:
                if self.page:
                    self.page.run_task(self._safe_update_failed, str(e))
                return
            if self.page:
                self.page.run_task(self._safe_quit_after_update)
        threading.Thread(target=_run, daemon=True).start()

    async def _safe_set_updating(self, text, percent):
        self.main_view.set_updating(text, percent)

    async def _safe_update_failed(self, err):
        self.main_view.close_updating()
        self.main_view.show_alert("העדכון נכשל", f"הורדת העדכון נכשלה:\n{err}", "error")

    async def _safe_quit_after_update(self):
        # Graceful close: triggers main_window's CLOSE handler (draft save +
        # embedded-browser teardown) before the installer takes over.
        await self.page.window.close()

    def _attach_events(self):
        self.main_view.bind_actions(
            on_run=self.on_run_click,
            on_stop=self.on_stop_click,
            on_settings=self.on_setting_click,
            on_close_handoff=self.close_handoff,
        )

    def close_handoff(self):
        """Close a handed-off TYPE 2 browser cleanly: driver.quit() shuts Chrome
        and chromedriver. No-op if there's no pending handoff."""
        dm, self._handoff_dm = self._handoff_dm, None
        if dm is not None:
            dm.close_driver()

    def on_setting_click(self, _event=None):
        self.settings_controller.open_settings(update_section=self.build_update_section())

    def on_stop_click(self, _event=None):
        self.worker_manager.stop()

    def on_run_click(self, _event=None):
        # Input always comes from the in-app entry grid (epic #14 / #18) —
        # typed or smart-pasted; there is no Excel-file input.
        source = self.main_view.get_manual_source()
        if source is None:
            return  # the grid is empty/invalid — main_view already alerted

        # TYPE 3 upsert writes to production irreversibly (creates sessions, syncs
        # attendance) — make the operator opt in each time. Compare (read-only) and
        # the other types start straight away.
        if str(parm.TYPE) == "3" and getattr(parm, "T3_MODE", T3_MODE_COMPARE) == T3_MODE_UPSERT:
            self.main_view.confirm(
                "לעדכן את הנוכחות במערכת?",
                "הפעולה תיצור מפגשים חסרים ותעדכן את הנוכחות לפי הטבלה — "
                "ולא ניתן לבטל אותה.",
                "כן, עדכן",
                lambda: self._start_run(source),
            )
            return
        self._start_run(source)

    def _start_run(self, source):
        # A pending TYPE 2 handoff still holds a live browser/driver — close it
        # cleanly before the new run starts (mirrors the old behaviour where
        # starting a run discarded an unfinished handoff, just without leaking it).
        self.close_handoff()

        started = self.worker_manager.start(source)
        if not started:
            return

        self.worker_manager.connect_signals(
            on_started=self.on_worker_started,
            on_finished=self.on_worker_finished,
            on_item_processed=self.on_item_processed,
            on_status=self.update_status,
            on_log=self.on_log,
            on_browser_ready=self.on_browser_ready,
            on_browser_detached=self.on_browser_detached,
        )
        self.worker_manager.start_thread()

    def on_log(self, line, level):
        # Debug channel → activity feed. enqueue_terminal_line is thread-safe
        # (it just puts on a queue drained by the UI loop), so no run_task needed.
        self.main_view.enqueue_terminal_line(line, level=level)

    def on_browser_ready(self, hwnd):
        # Chrome's window is up (issue #19) → embed it as an owned overlay over the
        # panel. Marshal onto the UI loop: it reads the Flet window's geometry and
        # stores overlay state owned by the UI thread.
        if self.page:
            self.page.run_task(self._safe_attach_browser, hwnd)
        else:
            self.main_view.attach_browser(hwnd)

    async def _safe_attach_browser(self, hwnd):
        self.main_view.attach_browser(hwnd)

    def on_browser_detached(self):
        # Run ended in 'action required': the driver (chromedriver + embedded
        # Chrome) was left fully alive. Capture it NOW — synchronously, on the
        # worker thread, before the worker is cleaned up — so it survives for a
        # clean close on "done"/next run. Then keep Chrome embedded in the panel.
        worker = self.worker_manager.worker
        if worker is not None:
            self._handoff_dm = worker.driver_manager
        if self.page:
            self.page.run_task(self._safe_detach_browser)
        else:
            self.main_view.enter_browser_handoff()

    async def _safe_detach_browser(self):
        self.main_view.enter_browser_handoff()

    def on_worker_started(self, total_items: int):
        self.total_items = max(1, total_items)
        self.current_item = 0
        # Status text is owned by the processor's milestone messages (e.g. the
        # per-row "מעבד שורה N…"); here we only seed the progress denominator.
        if self.page:
            self.page.run_task(self._safe_worker_started, total_items)
        else:
            self.main_view.set_progress(0.0, 0, self.total_items)

    async def _safe_worker_started(self, total_items):
        self.main_view.set_progress(0.0, 0, self.total_items)

    def on_item_processed(self):
        self.current_item += 1
        percentage = self.current_item / self.total_items
        if self.page:
            self.page.run_task(self._safe_update_progress, percentage, self.current_item, self.total_items)
        else:
            self.main_view.set_progress(percentage, self.current_item, self.total_items)

    async def _safe_update_progress(self, percentage, current, total):
        self.main_view.set_progress(percentage, current, total)

    def update_status(self, status, level=None):
        if self.page:
            self.page.run_task(self._safe_update_status, status, level)
        else:
            self.main_view.set_status(status, level=level)

    async def _safe_update_status(self, status, level=None):
        self.main_view.set_status(status, level=level)

    def on_worker_finished(self, success, message, detail="", summary=None):
        if self.page:
            self.page.run_task(self._safe_worker_finished, success, message, detail, summary)
        else:
            self._apply_finished(success, message, detail, summary)
            self.worker_manager.cleanup()

    async def _safe_worker_finished(self, success, message, detail="", summary=None):
        self._apply_finished(success, message, detail, summary)
        self.worker_manager.cleanup()

    def _apply_finished(self, success, message, detail="", summary=None):
        """Resolve the run's final UI state.

        On clean success the processor has already emitted its type-specific
        done message on the status channel (t1/t2/t3_done), so we only reset to
        idle and lock the progress at 100%. The controller owns just the two
        cases the processor can't speak to: a hard failure and a user stop.

        On failure the status field shows a short title (it is single-line and
        truncates), and a dialog carries the full actionable hint so it is never
        cut off.
        """
        self.worker_manager.set_idle_ui()
        if not success:
            self.main_view.set_status(Status.fatal_error(message), level="error")
            self.main_view.set_progress(0.0)
            # The status field is single-line; a dialog carries the full text so
            # the actionable hint is never truncated.
            full = f"{message}\n\n{detail}" if detail else message
            self.main_view.show_alert("התהליך נכשל", full, "error")
        elif message == "Execution Stopped":
            self.main_view.set_status(Status.stopped(self.current_item, self.total_items))
        else:
            self.main_view.set_progress(1.0)
            # Success speaks through the SAME alert component as a failure (one
            # unified completion language): a single dialog announces the result and
            # lists any problems (failed rows / unmatched IDs), with a copy button
            # for those IDs — so there's one completion surface, not a dialog plus a
            # separate card.
            if summary:
                body = Status.completion_body(summary)
                problems = summary.get("problem_ids") or []
                # The TYPE 3 compare/upsert report (summary["sections"]) is multi-
                # section prose, so make the whole rendered body copyable — but
                # strip the RTL display isolates so the pasted text is clean. The
                # legacy single-list path keeps copying just the raw IDs.
                if summary.get("sections"):
                    copy_text = strip_isolates(body)
                elif problems:
                    copy_text = "\n".join(str(x) for x in problems)
                else:
                    copy_text = None
                if self._handoff_dm is not None:
                    # TYPE 2 ended in handoff: the browser is still embedded for the
                    # operator's manual step. Don't cover it — arm the skipped-IDs
                    # dialog to fire once they click "סיימתי" (close the browser).
                    self.main_view.arm_handoff_summary(
                        Status.COMPLETED_TITLE, body, "success",
                        copy_text,
                    )
                else:
                    self.main_view.show_alert(
                        Status.COMPLETED_TITLE, body, "success",
                        copy_text=copy_text,
                        # Dismissing the completion dialog returns the hero to 'מוכן' —
                        # closing 'הושלם' readies the screen for the next run.
                        on_closed=self.main_view.reset_to_idle,
                    )

