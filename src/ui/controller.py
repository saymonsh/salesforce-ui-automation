import threading
import os
from src.core.config import config_instance as parm
from src.ui.settings_window import create_ui as s_ui, create_window as s_window
from src.automation.processors.login_processor import LoginProcessor
from src.automation.processors.candidate_processor import CandidateProcessor
from src.automation.processors.attendance_processor import AttendanceProcessor

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
            parm.reload() # Reload local copy
            
            # Sync back to controller state if needed
            self.uploaded_file_path = parm.UPLOADED_FILE_PATH
            self.main_ui["Text_uploadStatus"].text = "Saved"

        ui["SAVE"].on_click = on_save_click

    def update_ui_callback(self, status=None, progress=None, error=None):
        # This runs on the worker thread, but pyvisual often handles threading or needs signals.
        # Assuming direct property update is safe or safety is handled by pv/Qt.
        # Ideally should use signals if PySide6.
        # For this refactor, strictly mimicing original 'ui["key"].text = val' behavior.
        
        if status == "Done" or error:
             self.main_ui["Button_run"].is_visible = True
             self.main_ui["Progressbar"].is_visible = False
             self.main_ui["Text_running"].is_visible = False
             self.main_ui["Rectangle"].is_visible = False

        if status and status != "Done":
             self.main_ui["Text_uploadStatus"].text = status
        
        if progress is not None:
             self.main_ui["Progressbar"].value = progress

    def on_run_click(self, button=None):
        processor = None
        target_func = None

        if parm.TYPE == 1:
            print("Login in progress")
            processor = LoginProcessor(self.update_ui_callback)
            target_func = lambda: processor.process(self.uploaded_file_path)
            
        elif parm.TYPE == 2:
            print("Adding candidates")
            processor = CandidateProcessor(self.update_ui_callback)
            target_func = lambda: processor.process(self.uploaded_file_path)
            
        elif parm.TYPE == 3:
            print("test")
            processor = AttendanceProcessor(self.update_ui_callback)
            target_func = lambda: processor.process()
        else:
            print(parm.TYPE)

        if self.uploaded_file_path is None and parm.TYPE != 3:
            self.main_ui["Text_uploadStatus"].text = "❌ File not selected"
            return
        
        if parm.TYPE in [1, 2]:
            self.main_ui["Button_run"].is_visible = False
            self.main_ui["Progressbar"].is_visible = True
            self.main_ui["Text_running"].is_visible = True
            self.main_ui["Rectangle"].is_visible = True
            self.main_ui["Progressbar"].value = 0

        if target_func:
            thread = threading.Thread(target=target_func)
            thread.start()
