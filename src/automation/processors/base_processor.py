import threading
import pyotp
from abc import ABC, abstractmethod
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from src.automation.driver_manager import DriverManager
from src.automation import selectors as S
from src.core.config import config_instance as parm
from src.core.exceptions import StopRequestedException
from src.core.logger import logger
from src.core.status_messages import Status
from src.core.utils import interruptible_find_element


class BaseProcessor(ABC):
    def __init__(self, signals=None, driver_manager=None):
        self.signals = signals
        self.driver_manager = driver_manager
        self.stop_event = threading.Event()
        # When a run finishes leaving a manual step for the operator in the
        # browser (e.g. TYPE 2's final "next" in Salesforce), the processor sets
        # this so the worker leaves Chrome open instead of closing it.
        self.keep_browser_open = False

    def stop(self):
        """Signals the processor to stop execution."""
        self.stop_event.set()
        self.update_ui(status=Status.STOPPING)

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

    def update_ui(self, status=None, level=None):
        """Emit a high-level milestone on the status channel (issue #12).

        `level` (None / "success" / "warning" / "error") drives the status
        field's styling. Technical detail belongs on the debug channel (logger).
        """
        if self.signals and status:
            self.signals.status.emit(status, level)

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

        # Persistent stage so a timeout anywhere in the login flow (no per-step
        # logging happens during the blocking element waits) is classified as a
        # login failure rather than a generic one.
        logger.set_context(stage="login")
        self.update_ui(status=Status.LOGGING_IN)
        logger.info(f"navigating to {url}", stage="login")

        try:
            self.check_for_stop()
            self.driver.get(url)

            self.check_for_stop()
            # Skip maximize when Chrome is embedded as an owned overlay (issue #19):
            # maximizing a frameless owned popup blows it up to TRUE fullscreen
            # (even the taskbar vanishes) and it escapes the panel. The overlay
            # already sizes it, and a desktop-class --window-size covers the brief
            # pre-embed moment. Non-embedded runs still maximize for a full viewport.
            if not getattr(self.driver_manager, "on_browser_ready", None):
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
            logger.debug("submitting TOTP code", stage="login")
            tc = interruptible_find_element(self.driver, By.XPATH, S.LOGIN_TOTP_INPUT, check_stop_func=lambda: self.is_stopped)
            tc.send_keys(totp.now())

            self.check_for_stop()
            save = interruptible_find_element(self.driver, By.XPATH, S.LOGIN_TOTP_SAVE, check_stop_func=lambda: self.is_stopped)
            save.click()
        except TimeoutException:
            # An element never appeared. The most common real cause isn't a slow
            # page — it's Salesforce refusing the login (security policy / blocked
            # IP / bad credentials) and showing an error banner instead of
            # advancing. Surface that banner's text so the operator sees the real
            # reason (e.g. a VPN/IP block) rather than a bare timeout.
            banner = self._read_login_error()
            if banner:
                logger.error(f"login blocked by Salesforce: {banner}", stage="login")
                raise Exception(f"Salesforce login error: {banner}")
            raise

        logger.info("login OK — TOTP accepted", stage="login")
        self.update_ui(status=Status.MFA_OK)
        # Past login now; later phases set their own stage, but reset here so a
        # post-login pre-loop failure isn't mis-blamed on the login step.
        logger.set_context(stage="run")

    def _read_login_error(self):
        """Return the visible Salesforce login error banner text, or None.

        Used only on the login failure path. Uses a plain (non-blocking)
        find_elements — by this point the implicit wait is already 0 — so it
        never adds latency or stalls the stop mechanism.
        """
        try:
            for el in self.driver.find_elements(By.XPATH, S.LOGIN_ERROR_BANNER):
                text = (el.text or "").strip()
                if text:
                    return text
        except Exception:
            return None
        return None

    # =========================================================================
    # Shared Input Loading
    # =========================================================================

    def _load_rows(self, source):
        """
        Load tabular rows from a :class:`TabularSource` (issue #15) and apply the
        shared empty-input guard. Returns the ordered list of row dicts, or None
        if there are no rows (in which case the empty status is already emitted).

        The source decouples the processor from the input medium: today it is an
        Excel file, but the same guard serves a manual-entry grid unchanged.
        """
        rows = source.rows()

        if not rows:
            logger.error("input is empty — no rows to process", stage="run")
            self.update_ui(status=Status.FILE_EMPTY, level="error")
            return None

        logger.info(f"{len(rows)} rows loaded", stage="run")
        return rows
