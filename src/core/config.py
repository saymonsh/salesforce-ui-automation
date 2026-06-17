import configparser
import os
import sys

class Config:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        # Determine the project root directory (assuming this file is in src/core)
        # src/core/config.py -> ../../ -> project root
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        self.config_file_path = os.path.join(self.project_root, 'config.ini')

        if not os.path.exists(self.config_file_path):
             # Try falling back to current working directory if not found (dev convenience)
            if os.path.exists("config.ini"):
                self.config_file_path = os.path.abspath("config.ini")
            else:
                raise FileNotFoundError(f"Configuration file '{self.config_file_path}' not found. Please create it based on 'config.ini.example'.")

        self.parser = configparser.ConfigParser(interpolation=None)
        self.parser.read(self.config_file_path, encoding='utf-8')

        try:
            self.USER_NAME = self.parser['Auth']['USERNAME']
            self.PASSWORD = self.parser['Auth']['PASSWORD']
            self.SECRET_KEY = self.parser['Auth']['SECRET_KEY']

            self.URL = self.parser['Salesforce']['URL']
            try:
                self.TYPE = self.parser.getint('Salesforce', 'TYPE')
            except (ValueError, TypeError):
                self.TYPE = None

            # TYPE 3 sub-mode ("2" = compare-only / read-only, "3" = upsert).
            # Optional and read-only from config.ini — deliberately kept out of
            # validate() (via .get + fallback, never a bare subscript that would
            # raise KeyError) so an existing config.ini without it still loads and
            # it is never a required field.
            self.T3_MODE = self.parser.get('Salesforce', 'T3_MODE', fallback='2')

            self.ACT_DESCRIPTION = self.parser['Activity']['DESCRIPTION']
            self.ACT_NU = self.parser['Activity']['NUMBER']

            # Debug verbosity for the logging channel (issue #12). When False,
            # DEBUG-level lines (selectors, payloads, timings) are suppressed.
            self.DEBUG_LOGGING = self.parser.getboolean('Logging', 'DEBUG', fallback=False)

        except KeyError as e:
            raise KeyError(f"Missing configuration key: {e}")
        except Exception as e:
             raise ValueError(f"Error reading configuration: {e}")

    def validate(self):
        """
        Validates the current configuration based on the selected TYPE.
        Returns a list of missing or invalid parameter names.

        Input data always comes from the in-app entry grid (epic #14 / issue
        #18 — typed or smart-pasted, no Excel-file input), so there is no file
        path to validate here: only credentials, the system URL, and the TYPE-1
        activity fields.
        """
        errors = []

        # Global validations (credentials apply to every TYPE)
        if not self.USER_NAME: errors.append("שם משתמש (User Name)")
        if not self.PASSWORD: errors.append("סיסמה (Password)")
        if not self.SECRET_KEY: errors.append("מפתח סודי (Secret Key)")

        if self.TYPE is None:
            errors.append("סוג תהליך לא תקין או חסר (Type)")
            return errors # Cannot check specific logic if TYPE is unknown

        # Context-Aware Validations
        if self.TYPE == 1: # Login & Actions — logs in to a fixed home URL, so the
            # configurable system URL does not apply here.
            if not self.ACT_NU: errors.append("מספר פעילות (Activity Number)")
            if not self.ACT_DESCRIPTION: errors.append("תיאור פעילות (Description)")

        elif self.TYPE in (2, 3): # Candidates / Attendance — both navigate to URL.
            if not self.URL: errors.append("כתובת מערכת (URL)")

        return errors

    def reload(self):
        """Reloads the configuration from the file."""
        self._load_config()

    def update_config(self, section, key, value):
        """Updates a configuration value and saves to file."""
        if not self.parser.has_section(section):
            self.parser.add_section(section)
        self.parser[section][key] = str(value)
        
        with open(self.config_file_path, 'w', encoding='utf-8') as configfile:
            self.parser.write(configfile)
        
        # specific reload of attributes
        self._load_config()

# Global instance for easy import
config_instance = Config()
