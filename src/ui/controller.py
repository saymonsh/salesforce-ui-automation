import os
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QMessageBox
from src.core.config import config_instance as parm
from src.ui.settings_controller import SettingsController
from src.ui.worker_manager import WorkerManager


class Controller:
    """
    Main application controller. Acts as a thin coordinator that delegates to:
    - SettingsController: settings window management
    - WorkerManager: worker/thread lifecycle
    """

    def __init__(self, app, main_window, main_ui):
        self.app = app
        self.main_window = main_window
        self.main_ui = main_ui
        self.uploaded_file_path = parm.UPLOADED_FILE_PATH

        # Sub-controllers
        self.settings_controller = SettingsController(main_ui, self._show_alert)
        self.worker_manager = WorkerManager(main_ui, self._show_alert)

        self._attach_events()
        self._init_ui_state()

    def _init_ui_state(self):
         if self.uploaded_file_path:
            self.main_ui["FileDialog_fileUpload"].text = os.path.basename(self.uploaded_file_path)

    def _show_alert(self, parent, title, message, icon):
        msg_box = QMessageBox(parent)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(icon)
        # Detailed styling: White background for box, labels transparent (inherits white) or white. Text black.
        msg_box.setStyleSheet("QMessageBox { background-color: white; color: black; } QLabel { color: black; background-color: white; } QPushButton { color: black; background-color: #f0f0f0; border: 1px solid #c0c0c0; border-radius: 4px; padding: 5px; min-width: 60px; } QPushButton:hover { background-color: #e0e0e0; }")
        msg_box.exec()

    def _attach_events(self):
        self.main_ui["FileDialog_fileUpload"].on_file_selected = self.on_browse_button_click
        self.main_ui["Button_run"].on_click = self.on_run_click
        self.main_ui["Button_stop"].on_click = self.on_stop_click
        self.main_ui["Button_setting"].on_click = self.on_setting_click
        self.main_ui["Button_help"].on_click = self.on_help_click

    # =========================================================================
    # Event Handlers
    # =========================================================================

    def on_help_click(self, button=None):
        from src.ui.help_dialog import HelpDialog
        dialog = HelpDialog(self.main_window)
        dialog.exec()

    def on_browse_button_click(self, file_path):
        self.uploaded_file_path = file_path
        print(f"📂 File selected: {self.uploaded_file_path}")

    def on_setting_click(self, button=None):
        self.settings_controller.open_settings(self.main_window)
        # Sync back uploaded path after settings may have changed
        self.uploaded_file_path = parm.UPLOADED_FILE_PATH

    def on_stop_click(self, button=None):
        self.worker_manager.stop()

    def on_run_click(self, button=None):
        started = self.worker_manager.start(self.uploaded_file_path, self.main_window)
        if not started:
            return

        # Connect Signals
        self.worker_manager.connect_signals(
            on_finished=self.on_worker_finished,
            on_progress=self.update_progress,
            on_status=self.update_status
        )

        self.worker_manager.start_thread()

    # =========================================================================
    # Worker Signal Handlers
    # =========================================================================

    @Slot(int)
    def update_progress(self, value):
        self.main_ui["Progressbar"].value = value

    @Slot(str)
    def update_status(self, status):
        if status != "Done":
             self.main_ui["Text_mainStatus"].text = status

    @Slot(bool, str)
    def on_worker_finished(self, success, message):
        self.worker_manager.set_idle_ui()

        if not success:
            self.main_ui["Text_mainStatus"].text = "אירעה שגיאה"
            self._show_alert(self.main_window, "שגיאה", message, QMessageBox.Critical)
        else:
            if message and message not in ["Done", "Execution Stopped", "הפעולה הופסקה על ידי המשתמש."]:
                self.main_ui["Text_mainStatus"].text = "התהליך הושלם"
                self._show_alert(self.main_window, "דוח סיכום פעולה", message, QMessageBox.Information)
            else:
                self.main_ui["Text_mainStatus"].text = message

        # Cleanup
        self.worker_manager.cleanup()
