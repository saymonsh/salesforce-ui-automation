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
                print(f"Error: Configuration file '{self.config_file_path}' not found.")
                print("Please create it based on 'config.ini.example'.")
                sys.exit(1)

        self.parser = configparser.ConfigParser(interpolation=None)
        self.parser.read(self.config_file_path, encoding='utf-8')

        try:
            self.USER_NAME = self.parser['Auth']['USERNAME']
            self.PASSWORD = self.parser['Auth']['PASSWORD']
            self.SECRET_KEY = self.parser['Auth']['SECRET_KEY']

            self.URL = self.parser['Salesforce']['URL']
            self.TYPE = self.parser.getint('Salesforce', 'TYPE')

            self.ACT_DESCRIPTION = self.parser['Activity']['DESCRIPTION']
            self.ACT_NU = self.parser['Activity']['NUMBER']

            self.UPLOADED_FILE_PATH = self.parser.get('Paths', 'UPLOADED_FILE_PATH', fallback='')

        except KeyError as e:
            print(f"Error: Missing configuration key: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Error reading configuration: {e}")
            sys.exit(1)

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
