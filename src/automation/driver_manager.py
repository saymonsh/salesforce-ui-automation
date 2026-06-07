import os
import subprocess
import threading
from time import sleep
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from src.core.config import config_instance as config
from src.core.logger import logger

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
        # Capture chromedriver's own output so it streams into the activity feed
        # too (it's a separate process that otherwise writes straight to the OS
        # console, bypassing the Python stdout redirect). A reader thread also
        # prevents the pipe from filling and blocking the subprocess.
        self.chromedriver_process = subprocess.Popen(
            [chromedriver_path, "--port=9515"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
        threading.Thread(
            target=self._pump_output, args=(self.chromedriver_process,), daemon=True
        ).start()
        sleep(2)
        return self.chromedriver_process

    @staticmethod
    def _pump_output(proc):
        """Forward each chromedriver output line into the debug channel.

        chromedriver is a separate process; its raw lines are passed through
        verbatim (no timestamp/level prefix) so the exact driver output is
        visible in the feed/console.
        """
        try:
            for line in proc.stdout:
                line = line.rstrip("\n")
                if line.strip():
                    logger.debug(line, stage="chromedriver")
        except Exception:
            pass

    def create_driver(self):
        # Setup Proxy
        self.setup_proxy()

        # Options
        chrome_options = Options()
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-cookies")
        # Keep Chrome alive if chromedriver exits without an explicit quit. This is
        # what lets a run end in an 'action required' state with the window left
        # open for the operator (see detach_driver): we can terminate chromedriver
        # to free port 9515 for the next run without slamming the browser shut.
        # Normal completion still calls driver.quit(), which closes Chrome anyway.
        chrome_options.add_experimental_option("detach", True)
        logger.debug("chrome options set", stage="driver")

        chromedriver_url = "http://127.0.0.1:9515"
        self.driver = webdriver.Remote(
            command_executor=chromedriver_url,
            options=chrome_options
        )
        logger.info("chrome launched", stage="driver")
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
        logger.debug("chromedriver terminated", stage="driver")

    def detach_driver(self):
        """Release our handle on Chrome but leave the window open.

        Used when a run ends in an 'action required' state and the operator still
        has a manual step to finish in the browser. We deliberately do NOT call
        ``driver.quit()`` (that closes the window); instead we drop the session
        reference and terminate the chromedriver subprocess. Thanks to the
        ``detach`` option set in create_driver, killing chromedriver leaves Chrome
        standing while freeing port 9515 for the next run.
        """
        self.driver = None
        if self.chromedriver_process:
            try:
                self.chromedriver_process.terminate()
            except Exception:
                pass
            finally:
                self.chromedriver_process = None
        logger.debug("chromedriver detached — browser left open", stage="driver")
