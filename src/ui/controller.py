# import threading # Removed
import os
from PySide6.QtCore import QThread, Slot
from PySide6.QtWidgets import QMessageBox
from src.ui.worker import AutomationWorker
from src.core.config import config_instance as parm
from src.ui.settings_window import create_ui as s_ui, create_window as s_window
from src.automation.processors.login_processor import LoginProcessor
from src.automation.processors.candidate_processor import CandidateProcessor


class Controller:
    def __init__(self, app, main_window, main_ui):
        self.app = app
        self.main_window = main_window
        self.main_ui = main_ui
        self.settings_window = None
        self.uploaded_file_path = parm.UPLOADED_FILE_PATH
        
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
        self.main_ui["Button_setting"].on_click = self.on_setting_click

    def on_browse_button_click(self, file_path):
        self.uploaded_file_path = file_path
        print(f"📂 File selected: {self.uploaded_file_path}")

    def on_setting_click(self, button=None):
        if hasattr(self, "settings_window") and self.settings_window:
            self.settings_window.show()
        else:
            self.settings_window = s_window()
            settings_ui = s_ui(self.settings_window)
            self._attach_events_settings(settings_ui, self.settings_window)
            self.settings_window.show()

    def _attach_events_settings(self, ui, window):
        # Load values
        ui["USER_NAME"].text = parm.USER_NAME or ""
        ui["PASSWORD"].text = parm.PASSWORD or ""
        ui["SECRET_KEY"].text = parm.SECRET_KEY or ""
        ui["ACT_description"].text = parm.ACT_DESCRIPTION or ""
        ui["ACT_NU"].text = parm.ACT_NU or ""
        ui["URL"].text = parm.URL or ""
        ui["TYPE"].text = str(parm.TYPE or "")
        ui["UPLOADED_FILE_PATH"].text = parm.UPLOADED_FILE_PATH or ""

        def on_save_click(button=None):
            parm.update_config('Auth', 'USERNAME', ui["USER_NAME"].text)
            parm.update_config('Auth', 'PASSWORD', ui["PASSWORD"].text)
            parm.update_config('Auth', 'SECRET_KEY', ui["SECRET_KEY"].text)
            parm.update_config('Activity', 'DESCRIPTION', ui["ACT_description"].text)
            parm.update_config('Activity', 'NUMBER', ui["ACT_NU"].text)
            parm.update_config('Salesforce', 'URL', ui["URL"].text)
            parm.update_config('Salesforce', 'TYPE', ui["TYPE"].text)
            parm.update_config('Paths', 'UPLOADED_FILE_PATH', ui["UPLOADED_FILE_PATH"].text)
            
            window.close()
            parm.update_config('Paths', 'UPLOADED_FILE_PATH', ui["UPLOADED_FILE_PATH"].text)
            
            try:
                parm.reload() # Reload local copy
            except (ValueError, KeyError) as e:
                self._show_alert(window, "שגיאת הגדרות", f"שגיאה בשמירת ההגדרות:\n{str(e)}", QMessageBox.Critical)
                return
            
            # Sync back to controller state if needed
            self.uploaded_file_path = parm.UPLOADED_FILE_PATH
            self.main_ui["Text_uploadStatus"].text = "Saved"

        ui["SAVE"].on_click = on_save_click

    @Slot(int)
    def update_progress(self, value):
        self.main_ui["Progressbar"].value = value

    @Slot(str)
    def update_status(self, status):
        if status != "Done":
             self.main_ui["Text_uploadStatus"].text = status

    @Slot(bool, str)
    def on_worker_finished(self, success, message):
        self.main_ui["Button_run"].is_visible = True
        self.main_ui["Progressbar"].is_visible = False
        self.main_ui["Text_running"].is_visible = False
        self.main_ui["Rectangle"].is_visible = False

        if not success:
            self.main_ui["Text_uploadStatus"].text = f"Error: {message}"
        else:
             self.main_ui["Text_uploadStatus"].text = "Done"

        # Cleanup
        if hasattr(self, 'request_thread'):
             self.request_thread.quit()
             self.request_thread.wait()
             self.request_thread.deleteLater()
             self.request_thread = None
        if hasattr(self, 'worker'):
             self.worker.deleteLater()
             self.worker = None

    def on_run_click(self, button=None):
        if self.uploaded_file_path is None and parm.TYPE != 3:
            self.main_ui["Text_uploadStatus"].text = "❌ File not selected"
            return
        
        # Prepare UI
        # Prepare UI
        
        # Validation
        errors = parm.validate()
        if errors:
            error_msg = "הפרמטרים הבאים חסרים או שגויים עבור סוג התהליך שנבחר:\n\n• " + "\n• ".join(errors)
            self._show_alert(self.main_window, "הגדרות חסרות", error_msg, QMessageBox.Warning)
            return

        if parm.TYPE in [1, 2]:
            self.main_ui["Button_run"].is_visible = False
            self.main_ui["Progressbar"].is_visible = True
            self.main_ui["Text_running"].is_visible = True
            self.main_ui["Rectangle"].is_visible = True
            self.main_ui["Progressbar"].value = 0

        # Create Worker and Thread
        self.request_thread = QThread()
        
        if parm.TYPE == 1:
            print("Login in progress")
            self.worker = AutomationWorker(LoginProcessor, self.uploaded_file_path)
        elif parm.TYPE == 2:
            print("Adding candidates")
            self.worker = AutomationWorker(CandidateProcessor, self.uploaded_file_path)

        else:
             print(f"Unknown Type: {parm.TYPE}")
             return

        self.worker.moveToThread(self.request_thread)

        # Connect Signals
        self.request_thread.started.connect(self.worker.run)
        self.worker.signals.finished.connect(self.on_worker_finished)
        self.worker.signals.progress.connect(self.update_progress)
        self.worker.signals.status.connect(self.update_status)
        
        # Ensure thread cleanup happens when finished signal is emitted
        # We handle this in on_worker_finished, but can also connect finished to quit
        # self.worker.signals.finished.connect(self.request_thread.quit) # Done manually in on_worker_finished to ensure order

        self.request_thread.start()
