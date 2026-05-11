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

            self.ACT_DESCRIPTION = self.parser['Activity']['DESCRIPTION']
            self.ACT_NU = self.parser['Activity']['NUMBER']

            self.UPLOADED_FILE_PATH = self.parser.get('Paths', 'UPLOADED_FILE_PATH', fallback='')

        except KeyError as e:
            raise KeyError(f"Missing configuration key: {e}")
        except Exception as e:
             raise ValueError(f"Error reading configuration: {e}")

    def validate(self):
        """
        Validates the current configuration based on the selected TYPE.
        Returns a list of missing or invalid parameter names.
        """
        errors = []

        # Global validations
        if not self.USER_NAME: errors.append("שם משתמש (User Name)")
        if not self.PASSWORD: errors.append("סיסמה (Password)")
        if not self.SECRET_KEY: errors.append("מפתח סודי (Secret Key)")
        if not self.URL: errors.append("כתובת מערכת (URL)")
        
        if self.TYPE is None:
            errors.append("סוג תהליך לא תקין או חסר (Type)")
            return errors # Cannot check specific logic if TYPE is unknown

        # Context-Aware Validations
        if self.TYPE == 1: # Login & Actions
            if not self.UPLOADED_FILE_PATH: errors.append("נתיב לקובץ אקסל")
            if not self.ACT_NU: errors.append("מספר פעילות (Activity Number)")
            if not self.ACT_DESCRIPTION: errors.append("תיאור פעילות (Description)")

        elif self.TYPE == 2: # Candidates
            if not self.UPLOADED_FILE_PATH: errors.append("נתיב לקובץ אקסל")
            
        elif self.TYPE == 3: # Attendance Matrix
            if not self.UPLOADED_FILE_PATH: errors.append("נתיב לקובץ אקסל")
            
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
