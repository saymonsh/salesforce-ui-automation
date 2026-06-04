import threading
import pandas as pd
import pyotp
from abc import ABC, abstractmethod
from selenium.webdriver.common.by import By
from src.automation.driver_manager import DriverManager
from src.automation import selectors as S
from src.core.config import config_instance as parm
from src.core.exceptions import StopRequestedException
from src.core.utils import interruptible_find_element


class BaseProcessor(ABC):
    def __init__(self, signals=None, driver_manager=None):
        self.signals = signals
        self.driver_manager = driver_manager
        self.stop_event = threading.Event()

    def stop(self):
        """Signals the processor to stop execution."""
        self.stop_event.set()
        self.update_ui(status="Stopping...")

    def check_for_stop(self):
        if self.stop_event.is_set():
            raise StopRequestedException("Execution stopped by user")

    @property
    def is_stopped(self):
        return self.stop_event.is_set()

    @property
    def driver(self):
        return self.driver_manager.driver if self.driver_manager else None

    @abstractmethod
    def process(self, *args, **kwargs):
        pass

    def update_ui(self, status=None, progress=None, error=None):
        if self.signals:
            if status:
                self.signals.status.emit(status)
            if error:
                pass

    # =========================================================================
    # Shared Driver Lifecycle
    # =========================================================================

    def _setup_driver(self):
        """Launches chromedriver and creates the Selenium driver instance."""
        self.check_for_stop()
        self.driver_manager.launch_chromedriver()

        self.check_for_stop()
        self.driver_manager.create_driver()

    def _cleanup_driver(self):
        """Closes the driver and chromedriver subprocess. Safe to call twice."""
        if self.driver_manager:
            self.driver_manager.close_driver()

    def _force_close_driver(self):
        """Force-terminates the driver to break any blocking Selenium wait on stop."""
        self._cleanup_driver()

    # =========================================================================
    # Shared Login Flow
    # =========================================================================

    def _login(self, url):
        """
        Performs the full Salesforce login sequence: navigate, credentials, TOTP.
        All XPath selectors and wait timings are preserved exactly as-is.
        """
        secret_key = parm.SECRET_KEY
        totp = pyotp.TOTP(secret_key)

        self.check_for_stop()
        self.driver.get(url)

        self.check_for_stop()
        self.driver.maximize_window()

        self.check_for_stop()
        username = interruptible_find_element(self.driver, By.XPATH, S.LOGIN_USERNAME_INPUT, check_stop_func=lambda: self.is_stopped)
        username.send_keys(parm.USER_NAME)

        self.check_for_stop()
        password = interruptible_find_element(self.driver, By.XPATH, S.LOGIN_PASSWORD_INPUT, check_stop_func=lambda: self.is_stopped)
        password.send_keys(parm.PASSWORD)

        self.check_for_stop()
        submit = interruptible_find_element(self.driver, By.XPATH, S.LOGIN_SUBMIT_BUTTON, check_stop_func=lambda: self.is_stopped)
        submit.click()

        self.check_for_stop()
        tc = interruptible_find_element(self.driver, By.XPATH, S.LOGIN_TOTP_INPUT, check_stop_func=lambda: self.is_stopped)
        tc.send_keys(totp.now())

        self.check_for_stop()
        save = interruptible_find_element(self.driver, By.XPATH, S.LOGIN_TOTP_SAVE, check_stop_func=lambda: self.is_stopped)
        save.click()

    # =========================================================================
    # Shared Excel Reading
    # =========================================================================

    def _read_excel(self, uploaded_file_path):
        """
        Reads an Excel file and validates it is not empty.
        Returns the DataFrame, or None if the file is empty.
        """
        excel_data = pd.read_excel(uploaded_file_path)

        if len(excel_data) == 0:
            print("Excel file is empty.")
            self.update_ui(status="File is empty", error=True)
            return None

        return excel_data
