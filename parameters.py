import configparser
import os
import sys

# Define the config file path
CONFIG_FILE = 'config.ini'

# Check if config file exists
if not os.path.exists(CONFIG_FILE):
    print(f"Error: Configuration file '{CONFIG_FILE}' not found.")
    print("Please create it based on 'config.ini.example'.")
    sys.exit(1)

config = configparser.ConfigParser(interpolation=None)
config.read(CONFIG_FILE, encoding='utf-8')

try:
    USER_NAME = config['Auth']['USERNAME']
    PASSWORD = config['Auth']['PASSWORD']
    SECRET_KEY = config['Auth']['SECRET_KEY']

    URL = config['Salesforce']['URL']
    # TYPE was an integer in the original file
    TYPE = config.getint('Salesforce', 'TYPE')

    ACT_description = config['Activity']['DESCRIPTION']
    ACT_NU = config['Activity']['NUMBER']

    UPLOADED_FILE_PATH = config.get('Paths', 'UPLOADED_FILE_PATH', fallback='')

except KeyError as e:
    print(f"Error: Missing configuration key: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Error reading configuration: {e}")
    sys.exit(1)
