import pandas as pd
import pyotp
from abc import ABC, abstractmethod
from selenium.webdriver.common.by import By
from src.automation.driver_manager import DriverManager
from src.automation import selectors as S
from src.core.config import config_instance as parm
from src.core.utils import verify_running
from src.ui.worker import ProgressManager


class BaseProcessor(ABC):
    def __init__(self, signals=None):
        self.signals = signals
        self.is_stopped = False
        self.driver = None
        self.chromedriver_process = None
        self.progress_manager = ProgressManager(signals) if signals else None

    def stop(self):
        """Signals the processor to stop execution."""
        self.is_stopped = True
        self.update_ui(status="Stops Execution...")

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
        verify_running(lambda: self.is_stopped)
        self.chromedriver_process = DriverManager.launch_chromedriver()

        verify_running(lambda: self.is_stopped)
        self.driver = DriverManager.create_driver()

    def _cleanup_driver(self):
        """Quits the driver and terminates the chromedriver process."""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            finally:
                self.driver = None

        if self.chromedriver_process:
            self.chromedriver_process.terminate()
        print("chrome driver has been terminated")

    def _force_close_driver(self):
        """Force-closes the driver (used during stop/error handling)."""
        if self.driver:
            try:
                print("Forcing driver close due to stop...")
                self.driver.quit()
            except Exception as e:
                print(f"Error during forced driver close: {e}")
            finally:
                self.driver = None

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

        verify_running(lambda: self.is_stopped)
        self.driver.get(url)

        verify_running(lambda: self.is_stopped)
        self.driver.implicitly_wait(30)
        self.driver.maximize_window()

        verify_running(lambda: self.is_stopped)
        username = self.driver.find_element(By.XPATH, S.LOGIN_USERNAME_INPUT)
        username.send_keys(parm.USER_NAME)

        verify_running(lambda: self.is_stopped)
        password = self.driver.find_element(By.XPATH, S.LOGIN_PASSWORD_INPUT)
        password.send_keys(parm.PASSWORD)

        verify_running(lambda: self.is_stopped)
        self.driver.find_element(By.XPATH, S.LOGIN_SUBMIT_BUTTON).click()

        verify_running(lambda: self.is_stopped)
        tc = self.driver.find_element(By.XPATH, S.LOGIN_TOTP_INPUT)
        tc.send_keys(totp.now())

        verify_running(lambda: self.is_stopped)
        self.driver.find_element(By.XPATH, S.LOGIN_TOTP_SAVE).click()

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
