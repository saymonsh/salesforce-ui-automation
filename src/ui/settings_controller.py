from src.core.config import config_instance as parm
from src.ui.settings_window import SettingsFields, build_settings_view


class SettingsController:
    """Manages the settings dialog lifecycle, loading, and saving."""

    def __init__(self, page, main_view):
        self.page = page
        self.main_view = main_view

    def open_settings(self):
        settings_view, _fields = build_settings_view(
            initial_values={
                "USER_NAME": parm.USER_NAME or "",
                "PASSWORD": parm.PASSWORD or "",
                "SECRET_KEY": parm.SECRET_KEY or "",
                "ACT_DESCRIPTION": parm.ACT_DESCRIPTION or "",
                "ACT_NU": parm.ACT_NU or "",
                "URL": parm.URL or "",
                "TYPE": str(parm.TYPE or ""),
            },
            on_save=self._save_settings,
        )
        self.main_view.show_settings_view(settings_view)

    def _save_settings(self, fields: SettingsFields):
        parm.update_config("Auth", "USERNAME", fields.user_name.value)
        parm.update_config("Auth", "PASSWORD", fields.password.value)
        parm.update_config("Auth", "SECRET_KEY", fields.secret_key.value)
        parm.update_config("Activity", "DESCRIPTION", fields.act_description.value)
        parm.update_config("Activity", "NUMBER", fields.act_nu.value)
        parm.update_config("Salesforce", "URL", fields.url.value)
        parm.update_config("Salesforce", "TYPE", fields.type_value.value)

        try:
            parm.reload()
        except (ValueError, KeyError) as e:
            self.main_view.show_alert("שגיאת הגדרות", f"שגיאה בשמירת ההגדרות:\n{str(e)}", "error")
            return

        self.main_view.switch_to_main()
        self.main_view.set_status("Saved")
