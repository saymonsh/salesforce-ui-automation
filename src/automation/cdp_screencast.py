"""CDP screencast client (issue #19).

Mirrors the live Selenium-driven Chrome window into the app's own UI as a stream
of JPEG frames, using the Chrome DevTools Protocol over a WebSocket — *without*
disturbing the Selenium session that drives the automation.

Why a separate WebSocket (and not Selenium's CDP bridge): Selenium (via
chromedriver) owns one CDP client used to send the automation commands.
``Page.screencastFrame`` is delivered as a continuous stream of CDP *events*,
which a request/response helper like ``execute_cdp_cmd`` cannot receive. So we
open a SECOND, read-mostly WebSocket straight to the page target's debugger URL
and run ``Page.startScreencast`` there. Chrome happily serves multiple CDP
clients per target, so the two coexist: Selenium keeps clicking, we keep
receiving frames.

Scope: **view-only** for the first version (issue #19) — frames flow out, no
input is forwarded back. ``Input.dispatch*`` forwarding is a deliberate
follow-up, so the client is intentionally one-directional here.

Robustness: every network/parse failure is swallowed and reported via
``on_error`` (never raised), because the screencast is a non-essential overlay —
it must never be able to break a run. The discovery of the debugger address and
target is best-effort; if it fails, the panel simply stays on its placeholder.
"""
from __future__ import annotations

import json
import threading
import urllib.request
from typing import Callable, Optional

try:
    import websocket  # websocket-client
except Exception:  # pragma: no cover - dependency missing → screencast disabled
    websocket = None


class ScreencastClient:
    """Streams ``Page.screencastFrame`` JPEGs from a Chrome page target.

    Parameters
    ----------
    debugger_address:
        ``host:port`` of Chrome's remote-debugging endpoint (read from
        ``driver.capabilities['goog:chromeOptions']['debuggerAddress']``).
    on_frame:
        Called from the reader thread with each frame's raw base64 JPEG string
        (no ``data:`` prefix). Must be thread-safe and cheap — push to a queue
        and return; do not touch the UI synchronously here.
    on_error:
        Optional callback for a one-line diagnostic string (reader-thread).
    """

    # Cap the streamed frame to a desktop-class size: large enough that the
    # mirrored Salesforce UI stays legible, small enough to keep the base64
    # payload (and the Flet image bridge) light. The page viewport itself is
    # unchanged — this only bounds the captured image.
    MAX_WIDTH = 1366
    MAX_HEIGHT = 900
    QUALITY = 70  # JPEG quality 0–100; 70 is a good size/clarity trade-off.

    def __init__(
        self,
        debugger_address: str,
        on_frame: Callable[[str], None],
        on_error: Optional[Callable[[str], None]] = None,
    ):
        # Force IPv4: Chrome binds the debugger on 127.0.0.1, but the address (and
        # the webSocketDebuggerUrl it hands back) often says "localhost", which on
        # Windows resolves to IPv6 ::1 first — the WS connect then hangs until it
        # times out. Normalising to 127.0.0.1 everywhere avoids that.
        self._addr = (debugger_address or "").replace("localhost", "127.0.0.1")
        self._on_frame = on_frame
        self._on_error = on_error
        self._ws = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._msg_id = 0
        self._send_lock = threading.Lock()

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        """Begin streaming on a daemon thread. Safe no-op if already running or
        the websocket-client dependency is unavailable."""
        if self._running:
            return
        if websocket is None:
            self._report("websocket-client not installed — live preview disabled")
            return
        if not self._addr:
            self._report("no debugger address — live preview disabled")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="cdp-screencast", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop streaming and close the socket. Safe to call multiple times."""
        self._running = False
        # Best-effort: ask Chrome to stop the stream, then close. Closing the
        # socket also unblocks the reader thread's recv().
        try:
            self._send("Page.stopScreencast")
        except Exception:
            pass
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def bring_to_front(self) -> None:
        """Raise the real Chrome window/tab (``Page.bringToFront``).

        Used at the TYPE 2 'action required' handoff: the run leaves Chrome open
        for the operator to finish a manual step, so we surface that window from
        behind the app. Best-effort — failure just means the operator alt-tabs.
        """
        try:
            self._send("Page.bringToFront")
        except Exception:
            pass

    # ------------------------------------------------------------------ internals
    def _report(self, msg: str) -> None:
        if self._on_error:
            try:
                self._on_error(msg)
            except Exception:
                pass

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def _send(self, method: str, params: Optional[dict] = None) -> None:
        ws = self._ws
        if ws is None:
            return
        payload = json.dumps({"id": self._next_id(), "method": method, "params": params or {}})
        with self._send_lock:
            ws.send(payload)

    def _discover_ws_url(self) -> Optional[str]:
        """Find the page target's WebSocket debugger URL via the /json endpoint.

        Picks the first ``page`` target (the Salesforce tab). The target id is
        stable across navigations, so the URL stays valid for the whole run even
        as the page goes login → app.
        """
        try:
            with urllib.request.urlopen(f"http://{self._addr}/json", timeout=5) as resp:
                targets = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            self._report(f"could not query Chrome targets: {e}")
            return None
        def _ipv4(url):
            return url.replace("localhost", "127.0.0.1") if url else url

        for t in targets:
            if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                return _ipv4(t["webSocketDebuggerUrl"])
        # Fall back to any target that exposes a debugger URL.
        for t in targets:
            if t.get("webSocketDebuggerUrl"):
                return _ipv4(t["webSocketDebuggerUrl"])
        self._report("no debuggable page target found")
        return None

    def _run(self) -> None:
        ws_url = self._discover_ws_url()
        if not ws_url:
            self._running = False
            return
        try:
            self._ws = websocket.create_connection(ws_url, max_size=None, timeout=10)
            # A short recv timeout lets the read loop notice stop() (which closes
            # the socket) and periodically re-check _running even when idle.
            self._ws.settimeout(2)
        except Exception as e:
            self._report(f"screencast connect failed: {e}")
            self._running = False
            return

        try:
            self._send("Page.enable")
            self._send(
                "Page.startScreencast",
                {
                    "format": "jpeg",
                    "quality": self.QUALITY,
                    "maxWidth": self.MAX_WIDTH,
                    "maxHeight": self.MAX_HEIGHT,
                    "everyNthFrame": 1,
                },
            )
        except Exception as e:
            self._report(f"could not start screencast: {e}")
            self._running = False
            self.stop()
            return

        self._read_loop()

    def _read_loop(self) -> None:
        while self._running:
            try:
                raw = self._ws.recv()
            except websocket.WebSocketTimeoutException:
                continue  # idle tick — re-check _running
            except Exception:
                break  # socket closed (stop) or dropped
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("method") != "Page.screencastFrame":
                continue
            params = msg.get("params") or {}
            data = params.get("data")
            session_id = params.get("sessionId")
            # Ack first so Chrome keeps sending; an un-acked frame stalls the
            # stream after the in-flight buffer drains.
            if session_id is not None:
                try:
                    self._send("Page.screencastFrameAck", {"sessionId": session_id})
                except Exception:
                    break
            if data:
                try:
                    self._on_frame(data)
                except Exception:
                    pass
