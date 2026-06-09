import os
import subprocess
import threading
from time import sleep
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from src.automation.cdp_screencast import ScreencastClient
from src.automation.win_window import (
    hide_chrome_taskbar_button,
    restore_chrome_taskbar_button,
)
from src.core.config import config_instance as config
from src.core.logger import logger

class DriverManager:
    def __init__(self):
        self.driver = None
        self.chromedriver_process = None
        # Live-preview screencast (issue #19). When the host sets ``on_frame``
        # before create_driver(), Chrome's window is mirrored frame-by-frame into
        # the app's embedded browser panel. Left None → screencast disabled.
        self.on_frame = None
        self.screencast = None
        # Handle of the off-screen Chrome window whose taskbar button we stripped
        # (issue #19, Windows only). Kept so detach_driver can put it back.
        self.chrome_hwnd = None

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
        # Launch already parked off-screen so the window doesn't flash on the
        # desktop before _hide_window moves it (best-effort; _hide_window also
        # re-asserts the position in case Windows clamped it).
        chrome_options.add_argument("--window-position=-32000,-32000")
        # Keep Chrome alive if chromedriver exits without an explicit quit. This is
        # what lets a run end in an 'action required' state with the window left
        # open for the operator (see detach_driver): we can terminate chromedriver
        # to free port 9515 for the next run without slamming the browser shut.
        # Normal completion still calls driver.quit(), which closes Chrome anyway.
        chrome_options.add_experimental_option("detach", True)
        # Keep rendering (and thus the CDP screencast) alive while Chrome sits
        # off-screen / behind the app during a run. Modern Chrome throttles/freezes
        # painting of occluded or backgrounded windows, which would stall the live
        # preview (issue #19). These flags disable that throttling without
        # affecting the automation itself — load-bearing for the off-screen window.
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-features=CalculateNativeWindowOcclusion")
        # Chrome 111+ rejects DevTools WebSocket connections whose Origin isn't on
        # an allowlist (anti-DNS-rebinding). Our screencast client opens its own WS
        # to the debugger port, so it needs to be allowed. The port is bound to
        # localhost only, so permitting any origin here is local-scope.
        chrome_options.add_argument("--remote-allow-origins=*")
        logger.debug("chrome options set", stage="driver")

        chromedriver_url = "http://127.0.0.1:9515"
        self.driver = webdriver.Remote(
            command_executor=chromedriver_url,
            options=chrome_options
        )
        logger.info("chrome launched", stage="driver")
        self._start_screencast()
        # With the live preview wired, the operator watches Chrome inside the app's
        # embedded panel — a real Chrome window next to it is just noise. Park it
        # off-screen so only the panel shows it (kept headed, NOT headless, because
        # Salesforce's org login policy blocks headless logins). The screencast
        # keeps streaming regardless of window position (the occlusion/backgrounding
        # flags above keep it painting); detach_driver brings it back on-screen for
        # the TYPE 2 manual handoff. The taskbar button is suppressed separately.
        if self.on_frame:
            self._hide_window()
        return self.driver

    # Far enough off every monitor that Windows won't clamp it back on-screen
    # (the same magic offset Windows itself uses for minimized windows).
    _OFFSCREEN = (-32000, -32000)

    def _hide_window(self):
        """Move the real Chrome window off-screen and drop its taskbar button, so
        the operator only ever sees Chrome through the embedded panel."""
        try:
            self.driver.set_window_position(*self._OFFSCREEN)
            logger.debug("chrome window parked off-screen", stage="driver")
        except Exception:
            pass
        # Strip the taskbar button (Windows only, best-effort). The window stays
        # shown (off-screen) so it keeps painting for the screencast.
        pid = getattr(self.chromedriver_process, "pid", None)
        self.chrome_hwnd = hide_chrome_taskbar_button(pid)
        if self.chrome_hwnd:
            logger.debug("chrome taskbar button hidden", stage="driver")

    def _show_window(self):
        """Bring the real Chrome window back onto the visible desktop and restore
        its taskbar button (best-effort) — used at the TYPE 2 manual handoff."""
        # Put the taskbar button back first so the operator can find the window.
        restore_chrome_taskbar_button(self.chrome_hwnd)
        self.chrome_hwnd = None
        if not self.driver:
            return
        try:
            self.driver.set_window_position(0, 0)
        except Exception:
            pass

    # ---------------------------------------------------------------- screencast
    def _debugger_address(self):
        """Chrome's remote-debugging endpoint, auto-assigned by chromedriver and
        echoed back in the session capabilities. Returns ``host:port`` or None."""
        try:
            return self.driver.capabilities.get("goog:chromeOptions", {}).get("debuggerAddress")
        except Exception:
            return None

    def _start_screencast(self):
        """Mirror the live Chrome window into the app's browser panel (issue #19).

        Best-effort and fully optional: if no ``on_frame`` sink is wired, or the
        debugger address can't be read, the run proceeds exactly as before with
        no live preview. The screencast must never break automation.
        """
        if not self.on_frame:
            return
        addr = self._debugger_address()
        if not addr:
            logger.debug("no debuggerAddress — live preview disabled", stage="driver")
            return
        self.screencast = ScreencastClient(
            addr,
            on_frame=self.on_frame,
            on_error=lambda m: logger.debug(f"screencast: {m}", stage="driver"),
        )
        self.screencast.start()
        logger.debug(f"screencast started on {addr}", stage="driver")

    def _stop_screencast(self, bring_to_front=False):
        if self.screencast:
            try:
                if bring_to_front:
                    self.screencast.bring_to_front()
                self.screencast.stop()
            except Exception:
                pass
            finally:
                self.screencast = None

    def close_driver(self):
        # Tear the live preview down first — it holds its own WebSocket to Chrome.
        self._stop_screencast()
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None

        if self.chromedriver_process:
            try:
                self.chromedriver_process.terminate()
            except Exception:
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
        # Surface the (soon-to-be-orphaned) Chrome window from behind the app so
        # the operator can finish the manual step: bring it back on-screen (we
        # parked it off-screen for the live preview) and raise it, then drop the
        # live preview. Must run while we still hold the driver handle.
        self._show_window()
        self._stop_screencast(bring_to_front=True)
        self.driver = None
        if self.chromedriver_process:
            try:
                self.chromedriver_process.terminate()
            except Exception:
                pass
            finally:
                self.chromedriver_process = None
        logger.debug("chromedriver detached — browser left open", stage="driver")
