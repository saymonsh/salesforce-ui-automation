import os
import subprocess
import threading
from time import sleep
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from src.automation.win_window import (
    find_chrome_window,
    find_window_by_title,
    reframe_as_owned,
    window_pid,
)
from src.core.config import config_instance as config
from src.core.constants import APP_WINDOW_TITLE
from src.core.logger import logger


def cleanup_stray_automation_browsers():
    """Kill leftover automation Chrome/chromedriver from a previous session that
    didn't shut down cleanly — e.g. the app was X-ed mid-run, or it crashed. With
    detach=True the embedded Chrome is owned by the app window (so it closes with
    it), but the chromedriver subprocess can leak and keep port 9515 busy, and a
    handoff browser may survive. Targets ONLY automation processes (chromedriver,
    and chrome.exe launched with --enable-automation) — never the operator's own
    Chrome. Best-effort; called once at startup."""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "chromedriver.exe"],
                       capture_output=True, check=False)
    except Exception:
        pass
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
             "Where-Object { $_.CommandLine -match '--enable-automation' } | "
             "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
            capture_output=True, check=False)
    except Exception:
        pass

class DriverManager:
    def __init__(self):
        self.driver = None
        self.chromedriver_process = None
        # issue #19 (owned-overlay embedding). Once Chrome is up, its OS window
        # handle is reported through this callback so the UI can embed it as an
        # owned overlay over the browser panel. The UI owns the overlay lifecycle;
        # driver_manager only launches Chrome off-screen (so it never flashes on
        # the desktop before the UI grabs it) and hands over the handle.
        self.on_browser_ready = None
        self.chrome_hwnd = None
        # Browser-process pid (from the window) so close_driver can force the whole
        # Chrome process tree closed — with detach=True, driver.quit() does NOT
        # reliably close Chrome, which orphaned dozens of windows over a session.
        self.chrome_pid = None

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
        # Launch off-screen so the window never flashes on the desktop before the
        # UI embeds it into the panel (issue #19). The overlay moves it into place.
        chrome_options.add_argument("--window-position=-32000,-32000")
        # Desktop-class size so Salesforce Lightning renders its desktop layout
        # (the tuned selectors assume it) even before the overlay resizes the
        # window to the panel rect — we no longer maximize when embedding.
        chrome_options.add_argument("--window-size=1600,1000")
        # Render 1:1, ignoring the OS display scaling. Otherwise a 125%/150% scale
        # shrinks the CSS viewport (e.g. an 1161px panel → ~929 CSS px), dropping
        # Lightning BELOW its ~1024px desktop breakpoint into a narrow layout where
        # modals overlap buttons (ElementClickIntercepted). At 1:1 the CSS viewport
        # equals the physical panel width, keeping the tuned desktop layout.
        chrome_options.add_argument("--force-device-scale-factor=1")
        # Keep Chrome alive if chromedriver exits without an explicit quit. This is
        # what lets a run end in an 'action required' state with the window left
        # open for the operator (see detach_driver): we can terminate chromedriver
        # to free port 9515 for the next run without slamming the browser shut.
        # Normal completion still calls driver.quit(), which closes Chrome anyway.
        chrome_options.add_experimental_option("detach", True)
        # Defensive: keep the renderer painting even if the app window ever sits in
        # front of Chrome. The owned overlay normally stacks Chrome above the app,
        # but these flags cost nothing and avoid any throttling surprises.
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-features=CalculateNativeWindowOcclusion")
        logger.debug("chrome options set", stage="driver")

        chromedriver_url = "http://127.0.0.1:9515"
        self.driver = webdriver.Remote(
            command_executor=chromedriver_url,
            options=chrome_options
        )
        logger.info("chrome launched", stage="driver")
        self._report_browser_window()
        return self.driver

    # ------------------------------------------------------------- overlay handoff
    def _report_browser_window(self):
        """Locate Chrome's OS window and hand its handle to the UI (issue #19).

        Best-effort and optional: if no ``on_browser_ready`` sink is wired, or the
        window can't be found, the run proceeds with no embedded panel. Finding it
        can take a beat after the session is created, so we poll briefly.
        """
        if not self.on_browser_ready:
            return
        pid = getattr(self.chromedriver_process, "pid", None)
        if not pid:
            return
        hwnd = None
        for _ in range(80):  # up to ~8s for the window to materialise
            hwnd = find_chrome_window(pid)
            if hwnd:
                break
            sleep(0.1)
        self.chrome_hwnd = hwnd
        if not hwnd:
            logger.info("chrome window not found — no embedded panel", stage="driver")
            return
        self.chrome_pid = window_pid(hwnd)
        # Kill the taskbar flash: reframe Chrome as a frameless owned tool-window
        # the instant it's found (synchronously, in this worker thread) — the same
        # reframe the overlay does, but without waiting for the UI round-trip, so
        # the taskbar button is gone almost immediately instead of ~1s later.
        host = find_window_by_title(APP_WINDOW_TITLE)
        if host:
            # Pre-navigation (page is still data:,) — safe to do the hide→restyle→
            # show cycle that actually drops the already-shown taskbar button.
            reframe_as_owned(hwnd, host, hide_cycle=True)
        logger.info(f"chrome window {hwnd} ready for embedding", stage="driver")
        try:
            self.on_browser_ready(hwnd)
        except Exception as e:
            logger.info(f"on_browser_ready failed: {e}", stage="driver")

    def close_driver(self):
        # Kill Chrome's process tree FIRST. With detach=True (needed for the TYPE 2
        # handoff), driver.quit() does NOT reliably close Chrome — and if Chrome is
        # unresponsive, quit() can block, so doing it first would risk hanging here
        # and leaking the browser. Killing by pid up front guarantees the browser
        # is gone on every exit path, including a user 'stop'. No-op if already gone.
        if self.chrome_pid:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self.chrome_pid)],
                    capture_output=True, check=False,
                )
            except Exception:
                pass
            finally:
                self.chrome_pid = None
        self.chrome_hwnd = None

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
        standing while freeing port 9515 for the next run. The UI separately hands
        the window back to the operator as a normal standalone window (the overlay
        is released) so they can finish the manual step.
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
