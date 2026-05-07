import os
import subprocess
from time import sleep
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from src.core.config import config_instance as config

class DriverManager:
    def __init__(self):
        self.driver = None
        self.chromedriver_process = None

    @staticmethod
    def setup_proxy():
        os.environ.pop('HTTP_PROXY', None)
        os.environ.pop('HTTPS_PROXY', None)
        os.environ.pop('http_proxy', None)
        os.environ.pop('https_proxy', None)
        os.environ['NO_PROXY'] = '127.0.0.1,localhost'

    def launch_chromedriver(self):
        chromedriver_path = r"C:\chromedriver\chromedriver.exe"
        if not os.path.exists(chromedriver_path):
             # Fallback or error if needed, but for now strictly matching original
             pass
        self.chromedriver_process = subprocess.Popen([chromedriver_path, "--port=9515"])
        sleep(2)
        return self.chromedriver_process

    def create_driver(self):
        # Setup Proxy
        self.setup_proxy()

        # Options
        chrome_options = Options()
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-cookies")
        print("Chrome options set.")

        chromedriver_url = "http://127.0.0.1:9515"
        self.driver = webdriver.Remote(
            command_executor=chromedriver_url,
            options=chrome_options
        )
        print("Chrome launched.")
        return self.driver

    def close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                pass
            finally:
                self.driver = None

        if self.chromedriver_process:
            try:
                self.chromedriver_process.terminate()
            except Exception as e:
                pass
            finally:
                self.chromedriver_process = None
        print("chrome driver has been terminated")
