import os
import subprocess
from time import sleep
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from src.core.config import config_instance as config

class DriverManager:
    @staticmethod
    def setup_proxy():
        os.environ.pop('HTTP_PROXY', None)
        os.environ.pop('HTTPS_PROXY', None)
        os.environ.pop('http_proxy', None)
        os.environ.pop('https_proxy', None)
        os.environ['NO_PROXY'] = '127.0.0.1,localhost'

    @staticmethod
    def launch_chromedriver():
        chromedriver_path = r"C:\chromedriver\chromedriver.exe"
        if not os.path.exists(chromedriver_path):
             # Fallback or error if needed, but for now strictly matching original
             pass
        chromedriver_process = subprocess.Popen([chromedriver_path, "--port=9515"])
        sleep(2)
        return chromedriver_process

    @staticmethod
    def create_driver():
        # Setup Proxy
        DriverManager.setup_proxy()

        # Options
        chrome_options = Options()
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-cookies")
        print("Chrome options set.")

        chromedriver_url = "http://127.0.0.1:9515"
        driver = webdriver.Remote(
            command_executor=chromedriver_url,
            options=chrome_options
        )
        print("Chrome launched.")
        return driver
