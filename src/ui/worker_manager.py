import threading

from src.automation.processors.attendance_processor import AttendanceProcessor
from src.automation.processors.candidate_processor import CandidateProcessor
from src.automation.processors.login_processor import LoginProcessor
from src.core.config import config_instance as parm
from src.core.status_messages import Status
from src.ui.worker import AutomationWorker


class WorkerManager:
    """Manages worker lifecycle: creation, start, stop, and cleanup."""

    def __init__(self, main_view):
        self.main_view = main_view
        self.worker_thread = None
        self.worker = None

    def start(self, source, require_file=True):
        # `source` is a prebuilt data source (issue #15/#16): an Excel source in
        # file mode, or an in-memory source from the manual-entry grid. Its
        # presence is now the universal input guard for every TYPE.
        if source is None:
            self.main_view.set_status(Status.NO_FILE)
            return False

        errors = parm.validate(require_file=require_file)
        if errors:
            error_msg = "הפרמטרים הבאים חסרים או שגויים עבור סוג התהליך שנבחר:\n\n• " + "\n• ".join(errors)
            self.main_view.show_alert("שגיאת הגדרות", error_msg, "warning")
            return False

        if parm.TYPE == 1:
            self.worker = AutomationWorker(LoginProcessor, source)
        elif parm.TYPE == 2:
            self.worker = AutomationWorker(CandidateProcessor, source)
        elif parm.TYPE == 3:
            self.worker = AutomationWorker(AttendanceProcessor, source)
        else:
            self.main_view.show_alert("שגיאה", f"{parm.TYPE} איננו תהליך חוקי", "critical")
            return False

        # Switch to running-state UI (stop button + progress bar) now that a valid
        # worker exists — applies to all process types, including TYPE 3.
        self._set_running_ui(True)

        return True

    def connect_signals(self, on_started, on_finished, on_item_processed, on_status, on_log):
        if self.worker:
            self.worker.signals.started.connect(on_started)
            self.worker.signals.finished.connect(on_finished)
            self.worker.signals.item_processed.connect(on_item_processed)
            self.worker.signals.status.connect(on_status)
            self.worker.signals.log.connect(on_log)

    def start_thread(self):
        if self.worker:
            self.worker_thread = threading.Thread(target=self.worker.run, daemon=True)
            self.worker_thread.start()

    def stop(self):
        if self.worker:
            self.main_view.set_status(Status.STOPPING)
            self.worker.stop()
            self.main_view.disable_stop()

    def cleanup(self):
        self.worker = None
        self.worker_thread = None

    def _set_running_ui(self, running):
        self.main_view.set_running(running)

    def set_idle_ui(self):
        self._set_running_ui(False)
