import threading

from src.automation.processors.attendance_processor import AttendanceProcessor
from src.automation.processors.candidate_processor import CandidateProcessor
from src.automation.processors.login_processor import LoginProcessor
from src.core.config import config_instance as parm
from src.ui.worker import AutomationWorker


class WorkerManager:
    """Manages worker lifecycle: creation, start, stop, and cleanup."""

    def __init__(self, main_view):
        self.main_view = main_view
        self.worker_thread = None
        self.worker = None

    def start(self, uploaded_file_path):
        if uploaded_file_path is None and parm.TYPE != 3:
            self.main_view.set_status("File not selected")
            return False

        errors = parm.validate()
        if errors:
            error_msg = "הפרמטרים הבאים חסרים או שגויים עבור סוג התהליך שנבחר:\n\n• " + "\n• ".join(errors)
            self.main_view.show_alert("שגיאת הגדרות", error_msg, "warning")
            return False

        if parm.TYPE == 1:
            self.worker = AutomationWorker(LoginProcessor, uploaded_file_path)
        elif parm.TYPE == 2:
            self.worker = AutomationWorker(CandidateProcessor, uploaded_file_path)
        elif parm.TYPE == 3:
            print("Processing attendance matrix")
            self.worker = AutomationWorker(AttendanceProcessor, uploaded_file_path)
        else:
            self.main_view.show_alert("שגיאה", f"{parm.TYPE} איננו תהליך חוקי", "critical")
            return False

        # Switch to running-state UI (stop button + progress bar) now that a valid
        # worker exists — applies to all process types, including TYPE 3.
        self._set_running_ui(True)

        return True

    def connect_signals(self, on_started, on_finished, on_item_processed, on_status):
        if self.worker:
            self.worker.signals.started.connect(on_started)
            self.worker.signals.finished.connect(on_finished)
            self.worker.signals.item_processed.connect(on_item_processed)
            self.worker.signals.status.connect(on_status)

    def start_thread(self):
        if self.worker:
            self.worker_thread = threading.Thread(target=self.worker.run, daemon=True)
            self.worker_thread.start()

    def stop(self):
        if self.worker:
            self.main_view.set_status("Stopping...")
            self.worker.stop()
            self.main_view.disable_stop()

    def cleanup(self):
        self.worker = None
        self.worker_thread = None

    def _set_running_ui(self, running):
        self.main_view.set_running(running)

    def set_idle_ui(self):
        self._set_running_ui(False)
