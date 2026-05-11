from PySide6.QtCore import QThread, Slot
from PySide6.QtWidgets import QMessageBox
from src.ui.worker import AutomationWorker
from src.core.config import config_instance as parm
from src.automation.processors.login_processor import LoginProcessor
from src.automation.processors.candidate_processor import CandidateProcessor
from src.automation.processors.attendance_processor import AttendanceProcessor


class WorkerManager:
    """Manages worker thread lifecycle: creation, start, stop, and cleanup."""

    def __init__(self, main_ui, show_alert_fn):
        self.main_ui = main_ui
        self._show_alert = show_alert_fn
        self.request_thread = None
        self.worker = None

    def start(self, uploaded_file_path, parent_window):
        """
        Validates config, sets up UI for running state, creates worker thread,
        and starts the automation process.
        """
        if uploaded_file_path is None and parm.TYPE != 3:
            self.main_ui["Text_mainStatus"].text = "File not selected"
            return False

        # Validation
        errors = parm.validate()
        if errors:
            error_msg = "הפרמטרים הבאים חסרים או שגויים עבור סוג התהליך שנבחר:\n\n• " + "\n• ".join(errors)
            self._show_alert(parent_window, "שגיאת הגדרות", error_msg, QMessageBox.Warning)
            return False

        if parm.TYPE in [1, 2]:
            self._set_running_ui(True)

        # Create Worker and Thread
        self.request_thread = QThread()
        
        if parm.TYPE == 1:
            print("Login in progress")
            self.worker = AutomationWorker(LoginProcessor, uploaded_file_path)
        elif parm.TYPE == 2:
            print("Adding candidates")
            self.worker = AutomationWorker(CandidateProcessor, uploaded_file_path)
        elif parm.TYPE == 3:
            print("Processing attendance matrix")
            self.worker = AutomationWorker(AttendanceProcessor, uploaded_file_path)
        else:
            self._show_alert(parent_window, "שגיאה", f"{parm.TYPE} איננו תהליך חוקי", QMessageBox.Critical)
            return False

        self.worker.moveToThread(self.request_thread)

        # Connect Signals
        self.request_thread.started.connect(self.worker.run)

        return True

    def connect_signals(self, on_finished, on_progress, on_status):
        """Connects worker signals to controller slots."""
        if self.worker:
            self.worker.signals.finished.connect(on_finished)
            self.worker.signals.progress.connect(on_progress)
            self.worker.signals.status.connect(on_status)

    def start_thread(self):
        """Starts the worker thread."""
        if self.request_thread:
            self.request_thread.start()

    def stop(self):
        """Stops the running worker."""
        if self.worker:
            self.main_ui["Text_mainStatus"].text = "Stopping..."
            self.worker.stop()
            # Disable stop button to prevent multiple clicks
            self.main_ui["Button_stop"].is_disabled = True

    def cleanup(self):
        """Cleans up worker and thread after completion."""
        if self.request_thread:
            self.request_thread.quit()
            self.request_thread.wait()
            self.request_thread.deleteLater()
            self.request_thread = None
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def _set_running_ui(self, running):
        """Toggles UI elements between idle and running states."""
        self.main_ui["Button_run"].is_visible = not running
        self.main_ui["Button_stop"].is_visible = running
        if running:
            self.main_ui["Button_stop"].is_disabled = False
        self.main_ui["Progressbar"].is_visible = running
        self.main_ui["Text_running"].is_visible = running
        self.main_ui["Rectangle"].is_visible = running
        if running:
            self.main_ui["Progressbar"].value = 0

    def set_idle_ui(self):
        """Resets UI to idle state."""
        self._set_running_ui(False)
