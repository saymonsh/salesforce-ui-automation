from src.core.config import config_instance as parm
from src.core.constants import T3_MODE_COMPARE, T3_MODE_UPSERT
from src.core.status_messages import Status
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
        self.settings_controller.open_settings()

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

