from PySide6.QtWidgets import QMessageBox
from src.core.config import config_instance as parm
from src.ui.settings_window import create_ui as s_ui, create_window as s_window


class SettingsController:
    """Manages the settings window lifecycle, loading, and saving."""

    def __init__(self, main_ui, show_alert_fn):
        self.main_ui = main_ui
        self._show_alert = show_alert_fn
        self.settings_window = None

    def open_settings(self, parent_window):
        """Opens or re-shows the settings window."""
        if self.settings_window:
            self.settings_window.show()
        else:
            self.settings_window = s_window()
            settings_ui = s_ui(self.settings_window)
            self._attach_events(settings_ui, self.settings_window)
            self.settings_window.show()

    def _attach_events(self, ui, window):
        """Loads current config values into settings UI and binds save."""
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
            
            self.main_ui["Text_mainStatus"].text = "Saved"

        ui["SAVE"].on_click = on_save_click

    def get_uploaded_file_path(self):
        """Returns the current uploaded file path from config."""
        return parm.UPLOADED_FILE_PATH
