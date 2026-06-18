import os
import subprocess
import threading
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from src.automation.win_window import (
    find_chrome_window,
    find_offscreen_chrome_window,
    find_window_by_title,
    reframe_as_owned,
)
from src.core.config import config_instance as config
from src.core.constants import APP_WINDOW_TITLE
from src.core.logger import logger
from src.core.utils import smart_sleep


class DriverManager:
    """Owns the chromedriver/Chrome lifecycle.

    Driver acquisition history (the machine this runs on is a managed
    government/municipal Windows box behind a proxy):

    * The PROBLEM that shaped the original design: `webdriver-manager` / any tool
      that honours the proxy environment crashed here. We chased it down (see the
      `diag/netfree-machine` investigation) and the real cause was a **stray
      User-scope `HTTP_PROXY` env var** pointing at a dead box — Python read it
      (env is consulted before the registry), the browser didn't. It was never
      certs, never a blocked CDN, never the port.
    * The OLD workaround: ship a hardcoded `C:\\chromedriver\\chromedriver.exe`,
      launch it as a subprocess on a fixed `--port=9515`, and avoid all downloads.
      That "worked" only by sidestepping the network; 9515 was a coincidence, not a
      fix. The one thing that genuinely mattered was `setup_proxy()` stripping the
      proxy so the *localhost* WebDriver call goes direct.
    * The CURRENT approach: let **Selenium Manager** (built into Selenium 4.6+)
      resolve and, if needed, download the chromedriver matching the installed
      Chrome. We proved it works here (incl. a cold download) once the proxy is
      stripped. This drops the hardcoded path, the manual subprocess, the fixed
      port, and the version-drift maintenance. `setup_proxy()` stays — it's the
      actual load-bearing piece. Edge case (Chrome updated *and* direct egress
      closed at the same moment): acquisition fails with a clear recovery hint
      rather than a cryptic crash; recovery is to run with direct egress or drop a
      matching chromedriver on PATH.
    """

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
        # Cooperative stop hook (set by the processor before create_driver). Lets
        # the off-screen window poll below honour the Stop button instead of
        # blocking on a bare sleep — None means "no check" (behaves as before).
        self.check_stop = None
        # The embed handoff runs from two racers — a concurrent off-screen poller
        # (kills the taskbar flash) and the post-build pid-based fallback. This
        # guards it so only the first to find the window wins.
        self._embed_lock = threading.Lock()
        self._embedded = False

    @staticmethod
    def setup_proxy():
        """Strip any proxy from the environment and exempt localhost.

        LOAD-BEARING — do not remove. On the managed deployment machine a stray/org
        proxy in the environment otherwise (a) routes the *localhost* WebDriver call
        through a filter that mangles the reply into non-JSON ("'str' object has no
        attribute 'get'"), and (b) can break Selenium Manager's driver download.
        Stripping it here is the piece that actually made driver setup work — see the
        class docstring.
        """
        os.environ.pop('HTTP_PROXY', None)
        os.environ.pop('HTTPS_PROXY', None)
        os.environ.pop('http_proxy', None)
        os.environ.pop('https_proxy', None)
        os.environ['NO_PROXY'] = '127.0.0.1,localhost'

    def launch_chromedriver(self):
        """No-op, kept for interface symmetry (``_setup_driver`` and
        ``DemoDriverManager`` both call it). There's no separate subprocess to
        pre-spawn anymore: Selenium Manager launches chromedriver inside
        ``create_driver()`` on a free port it picks itself."""
        return None

    def create_driver(self):
        # Strip the proxy BEFORE building the driver (see setup_proxy docstring).
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
        # NOTE: detach is deliberately OFF. With it on, driver.quit() didn't
        # reliably close Chrome and every run leaked a browser. The TYPE 2 handoff
        # instead keeps the whole driver alive (the controller holds it) and closes
        # it gracefully when the operator is done — see worker.run / controller.
        # Defensive: keep the renderer painting even if the app window ever sits in
        # front of Chrome. The owned overlay normally stacks Chrome above the app,
        # but these flags cost nothing and avoid any throttling surprises.
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-features=CalculateNativeWindowOcclusion")
        logger.debug("chrome options set", stage="driver")

        # Catch the taskbar flash: webdriver.Chrome() below takes ~2-3s and Chrome's
        # window becomes visible (with a taskbar button) partway through — but we
        # can't reframe it until the call returns and yields the pid. So start a
        # concurrent poller that finds the window by its off-screen position (no pid
        # needed) and reframes it the instant it appears, mid-build. The post-build
        # pid path stays as the fallback; _embed_window lets only the first win.
        self._embedded = False
        if self.on_browser_ready:
            threading.Thread(target=self._early_embed, daemon=True).start()

        # Selenium Manager (built into Selenium 4.6+) resolves — and if needed
        # downloads — the chromedriver matching the installed Chrome, then Service
        # launches it on a free port. No hardcoded path, no version pin, no fixed
        # port. The NO_PROXY set above keeps that localhost connection direct.
        #
        # log_output=DEVNULL — do NOT pipe chromedriver's output. A PIPE nobody
        # drains fast enough fills its OS buffer, blocks chromedriver, and every
        # WebDriver call then hangs in a blocking socket read — which also wedges
        # the cooperative Stop (it can't poll the stop flag mid-read). DEVNULL is
        # the safe choice; chromedriver chatter isn't worth that risk. (For one-off
        # driver debugging, point log_output at a file instead — never a PIPE.)
        service = Service(log_output=subprocess.DEVNULL)
        try:
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            # The edge case (Chrome updated AND direct egress closed at once): make
            # the failure legible and point at recovery instead of crashing opaquely.
            logger.error(
                f"chromedriver acquisition/launch failed ({type(e).__name__}: {e}). "
                "Selenium Manager needs direct internet for the matching driver. "
                "Recovery: run with direct egress (proxy stripped — setup_proxy does "
                "this), or place a matching chromedriver on PATH / set SE_CHROMEDRIVER.",
                stage="driver", exc=True,
            )
            self._embedded = True  # stop the concurrent poller embedding a dying window
            raise
        # Hand the chromedriver process to the rest of the lifecycle: the embedding
        # locates Chrome by this PID, and close_driver terminates it as a watchdog.
        self.chromedriver_process = self.driver.service.process
        logger.info("chrome launched", stage="driver")
        self._report_browser_window()
        return self.driver

    # ------------------------------------------------------------- overlay handoff
    def _embed_window(self, hwnd):
        """Reframe Chrome as a frameless owned tool-window (drops the taskbar button
        via ITaskbarList::DeleteTab — no hide, so no page-stall risk) and hand the
        handle to the UI. Idempotent: the concurrent off-screen poller and the
        post-build pid fallback both call this; the lock lets only the first win."""
        with self._embed_lock:
            if self._embedded:
                return
            self._embedded = True
        self.chrome_hwnd = hwnd
        host = find_window_by_title(APP_WINDOW_TITLE)
        if host:
            reframe_as_owned(hwnd, host)
        logger.debug(f"chrome window {hwnd} ready for embedding (host={'found' if host else 'MISSING'})",
                     stage="driver")
        try:
            self.on_browser_ready(hwnd)
        except Exception as e:
            logger.debug(f"on_browser_ready failed: {e}", stage="driver")

    def _early_embed(self):
        """Concurrent with webdriver.Chrome(): find the off-screen Chrome window by
        POSITION (no pid needed) and embed it the instant it's visible, so the
        taskbar button is dropped with no perceptible flash. Best-effort; honours
        Stop; the pid-based ``_report_browser_window`` is the fallback."""
        for _ in range(400):  # ~12s at 30ms — covers a slow first-launch build
            if self._embedded:
                return
            hwnd = find_offscreen_chrome_window()
            if hwnd:
                logger.debug("chrome window caught off-screen (concurrent embed path)", stage="driver")
                self._embed_window(hwnd)
                return
            try:
                smart_sleep(0.03, self.check_stop, interval=0.03)
            except Exception:
                return  # Stop requested or driver tearing down — let the main path handle it

    def _report_browser_window(self):
        """Pid-based fallback handoff: if the concurrent off-screen poller didn't
        already embed (e.g. the window wasn't parked where expected), find Chrome by
        the chromedriver pid and embed it. No-op if the early poller already won."""
        if not self.on_browser_ready or self._embedded:
            return
        pid = getattr(self.chromedriver_process, "pid", None)
        if not pid:
            return
        hwnd = None
        for _ in range(80):  # up to ~8s for the window to materialise
            if self._embedded:
                return
            hwnd = find_chrome_window(pid)
            if hwnd:
                break
            # Cooperative wait: honours the Stop button mid-poll (raises
            # StopRequestedException), unlike a bare sleep — see CLAUDE.md (#6).
            smart_sleep(0.1, self.check_stop, interval=0.1)
        if not hwnd:
            logger.debug("chrome window not found — no embedded panel", stage="driver")
            return
        self._embed_window(hwnd)

    def close_driver(self):
        """Close the browser fast and fully by killing the chromedriver process TREE
        (chromedriver + its child Chrome processes).

        Runs on Stop / handoff "done" / before a new run — sometimes on the UI thread
        — so it must be snappy and must never hang. We deliberately DON'T call
        ``driver.quit()``: with Selenium Manager's Service, quit() WAITS ~2.5s for the
        service to stop, which made Stop/"done" feel sluggish. A tree-kill by our own
        chromedriver PID closes everything in well under a second and can't wedge the
        UI (#8). It's keyed off the PID of the chromedriver process we created here,
        so — unlike a stored HWND — it can never touch an unrelated process.

        ponytail: the abrupt kill skips Chrome's graceful temp-profile cleanup, so a
        small user-data dir leaks into %TEMP% per run. Acceptable for an
        occasional-run desktop tool; upgrade path is a fire-and-forget background
        ``driver.quit()`` before the kill if that ever matters.
        """
        pid = getattr(self.chromedriver_process, "pid", None)
        self.driver = None
        self.chromedriver_process = None
        self.chrome_hwnd = None
        if not pid:
            return
        try:
            # /T kills the whole tree (chromedriver + Chrome); /F forces it. Bounded
            # so a stuck taskkill can't hang the caller. taskkill is a Windows builtin.
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, timeout=5)
            logger.debug(f"driver closed — killed chromedriver tree (pid {pid})", stage="driver")
        except Exception as e:
            logger.debug(f"close_driver taskkill failed: {e}", stage="driver")
