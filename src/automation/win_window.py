"""Win32 toolkit to embed the automation Chrome window inside the Flet app
(issue #19, "owned-overlay" approach — validated by spikes/reparent_spike.py).

Why this and not the CDP screencast it replaces: the screencast was a blurry
JPEG mirror that also forced us to hide the real Chrome (mirror + off-screen +
taskbar-hide = scattered hacks). Instead we show the REAL Chrome window, natively
rendered, right over the app's browser panel.

The validated mechanism (do NOT switch to ``SetParent``/``WS_CHILD`` — that
breaks keyboard input across processes; AttachThreadInput doesn't rescue it):
make Chrome a **frameless, OWNED top-level window** of the Flet window via
``GWLP_HWNDPARENT``, and keep it positioned over the panel rectangle. As a real
top-level window Chrome keeps its own native focus/keyboard/mouse handling; the
owner relationship gives the embedded feel — no taskbar button, minimizes and
closes with the app, always stacked above it. A ~100 Hz tracker thread keeps it
glued to the panel as the window moves/resizes (Flet only reports resize on
drag-release, which lags).

Everything here is Windows-only and strictly best-effort: failures are swallowed
so they can never break a run. On non-Windows the public API degrades to no-ops.
"""
from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes
from typing import Callable, Optional, Set, Tuple

try:
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
except Exception:  # pragma: no cover - non-Windows: helpers degrade to no-ops
    _user32 = None
    _kernel32 = None

# --- Win32 constants -------------------------------------------------------
GWL_STYLE = -16
GWL_EXSTYLE = -20
GWLP_HWNDPARENT = -8  # sets a top-level window's OWNER (not a child parent)
WS_EX_TOOLWINDOW = 0x00000080  # not shown in the taskbar
WS_EX_APPWINDOW = 0x00040000   # forced into the taskbar
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000
WS_OVERLAPPEDWINDOW = 0x00CF0000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
HWND_TOP = 0
SW_HIDE = 0
SW_SHOW = 5
SW_SHOWNA = 8
SW_RESTORE = 9
WM_CLOSE = 0x0010
GW_OWNER = 4
TH32CS_SNAPPROCESS = 0x00000002
_INVALID_HANDLE = ctypes.c_void_p(-1).value
_CHROME_WINDOW_CLASS = "Chrome_WidgetWin_1"
# A point far off every monitor — where Chrome is parked while hidden.
_OFFSCREEN = (-32000, -32000)

if _user32 is not None:
    _GetWindowLong = getattr(_user32, "GetWindowLongPtrW", None) or _user32.GetWindowLongW
    _SetWindowLong = getattr(_user32, "SetWindowLongPtrW", None) or _user32.SetWindowLongW
    _GetWindowLong.restype = ctypes.c_ssize_t
    _GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
    _SetWindowLong.restype = ctypes.c_ssize_t
    _SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _user32.GetWindow.restype = wintypes.HWND
    _user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsZoomed.restype = wintypes.BOOL
    _user32.IsZoomed.argtypes = [wintypes.HWND]
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetClassNameW.restype = ctypes.c_int
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.ShowWindow.restype = wintypes.BOOL
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    try:
        _user32.GetDpiForWindow.restype = wintypes.UINT
        _user32.GetDpiForWindow.argtypes = [wintypes.HWND]
    except Exception:  # pragma: no cover - pre-Win10
        pass
    _user32.PostMessageW.restype = wintypes.BOOL
    _user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                     wintypes.WPARAM, wintypes.LPARAM]
    _WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL


def close_window(hwnd: Optional[int]) -> None:
    """Politely close a window (WM_CLOSE) — used to shut the handoff Chrome from
    the panel's close button after the operator finished the manual step.
    Best-effort no-op if hwnd is gone or we're not on Windows."""
    if _user32 is None or not hwnd:
        return
    try:
        _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    except Exception:
        pass


def set_process_dpi_aware() -> None:
    """Make OUR process per-monitor-DPI-aware (v2) so our Win32 coordinates live
    in the same physical-pixel space as Flutter. Without this Windows virtualizes
    our coords and the overlay lands in the wrong place on scaled displays. Safe
    to call repeatedly (only the first wins; later calls just fail harmlessly)."""
    if _user32 is None:
        return
    try:
        _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass


# --------------------------------------------------------------- window finders
class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


def _child_chrome_pids(parent_pid: int) -> Set[int]:
    """PIDs of ``chrome.exe`` processes whose parent is ``parent_pid`` — Chrome's
    browser process, which owns the top-level window. Matching by process (not
    title/position) avoids grabbing one of the user's own Chrome windows."""
    pids: Set[int] = set()
    if _kernel32 is None:
        return pids
    snap = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == _INVALID_HANDLE:
        return pids
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        ok = _kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if (entry.th32ParentProcessID == parent_pid
                    and (entry.szExeFile or "").lower() == "chrome.exe"):
                pids.add(entry.th32ProcessID)
            ok = _kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _kernel32.CloseHandle(snap)
    return pids


def _visible_top_level(pids: Optional[Set[int]], want_class: Optional[str],
                       want_title: Optional[str]) -> Optional[int]:
    """First visible, un-owned top-level window matching the given filters."""
    if _user32 is None:
        return None
    found = []

    def _cb(hwnd, _l):
        try:
            if not _user32.IsWindowVisible(hwnd):
                return True
            if _user32.GetWindow(hwnd, GW_OWNER):
                return True
            if pids is not None:
                pid = wintypes.DWORD()
                _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value not in pids:
                    return True
            if want_class is not None:
                buf = ctypes.create_unicode_buffer(64)
                _user32.GetClassNameW(hwnd, buf, 64)
                if buf.value != want_class:
                    return True
            if want_title is not None:
                buf = ctypes.create_unicode_buffer(512)
                _user32.GetWindowTextW(hwnd, buf, 512)
                if buf.value != want_title:
                    return True
            found.append(hwnd)
            return False
        except Exception:
            return True

    try:
        _user32.EnumWindows(_WNDENUMPROC(_cb), 0)
    except Exception:
        return None
    return found[0] if found else None


def find_chrome_window(chromedriver_pid: int) -> Optional[int]:
    """The automation browser's main window (best-effort, Windows only)."""
    if _user32 is None or not chromedriver_pid:
        return None
    return _visible_top_level(_child_chrome_pids(chromedriver_pid),
                              _CHROME_WINDOW_CLASS, None)


def find_window_by_title(title: str) -> Optional[int]:
    """The app's own (Flutter) host window, located by its exact title."""
    if _user32 is None or not title:
        return None
    return _visible_top_level(None, None, title)


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


_CLSID_TaskbarList = "{56FDF344-FD6D-11D0-958A-006097C9A090}"
_IID_ITaskbarList = "{56FDF342-FD6D-11D0-958A-006097C9A090}"


def delete_taskbar_button(hwnd: Optional[int]) -> None:
    """Remove a window's taskbar button at runtime via the shell's ITaskbarList
    (``DeleteTab``) — the documented API for exactly this. Unlike a hide→show
    cycle it does NOT touch the window, so it can't stall a loading page and has
    no pre-navigation timing dependency. Works cross-process. Best-effort.

    COM-via-ctypes: CoCreateInstance gives an interface pointer whose first field
    is the vtable; we call by vtable slot (IUnknown 0-2, then HrInit=3 … DeleteTab=5).
    """
    if _user32 is None or not hwnd:
        return
    ole32 = ctypes.windll.ole32
    co_inited = False
    try:
        ole32.CLSIDFromString.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(_GUID)]
        ole32.CLSIDFromString.restype = ctypes.c_long
        ole32.CoCreateInstance.argtypes = [
            ctypes.POINTER(_GUID), ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p),
        ]
        ole32.CoCreateInstance.restype = ctypes.c_long
        ole32.CoInitialize.argtypes = [ctypes.c_void_p]
        ole32.CoInitialize.restype = ctypes.c_long

        hr = ole32.CoInitialize(None)
        co_inited = hr in (0, 1)  # S_OK / S_FALSE — both need a matching uninit
        clsid, iid = _GUID(), _GUID()
        if ole32.CLSIDFromString(_CLSID_TaskbarList, ctypes.byref(clsid)) != 0:
            return
        if ole32.CLSIDFromString(_IID_ITaskbarList, ctypes.byref(iid)) != 0:
            return
        ptr = ctypes.c_void_p()
        CLSCTX_INPROC_SERVER = 1
        if ole32.CoCreateInstance(ctypes.byref(clsid), None, CLSCTX_INPROC_SERVER,
                                  ctypes.byref(iid), ctypes.byref(ptr)) != 0 or not ptr.value:
            return
        vtable_addr = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0]
        vtable = ctypes.cast(ctypes.c_void_p(vtable_addr), ctypes.POINTER(ctypes.c_void_p))
        _hrinit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtable[3])
        _deltab = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND)(vtable[5])
        _release = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtable[2])
        _hrinit(ptr)
        _deltab(ptr, hwnd)
        _release(ptr)
    except Exception:
        pass
    finally:
        if co_inited:
            try:
                ole32.CoUninitialize()
            except Exception:
                pass


def reframe_as_owned(chrome_hwnd: Optional[int], host_hwnd: Optional[int]) -> bool:
    """Strip Chrome's frame and make it a frameless, OWNED tool-window popup of
    ``host_hwnd``, then drop its taskbar button via the shell (``delete_taskbar_
    button``). Shared by the early driver-side suppression (the instant the window
    is found) and by the overlay. No hide/show — nothing can stall the page, and
    there's no pre-navigation timing dependency. Best-effort.
    """
    if _user32 is None or not chrome_hwnd or not host_hwnd:
        return False
    try:
        style = _GetWindowLong(chrome_hwnd, GWL_STYLE)
        style &= ~(WS_CHILD | WS_OVERLAPPEDWINDOW | WS_CAPTION | WS_THICKFRAME
                   | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)
        style |= WS_POPUP
        _SetWindowLong(chrome_hwnd, GWL_STYLE, style)
        # Tool-window (clear APPWINDOW) so the shell won't re-add the button, owner
        # for the embedded relationship, FRAMECHANGED to apply the new frame.
        ex = _GetWindowLong(chrome_hwnd, GWL_EXSTYLE)
        ex = (ex & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
        _SetWindowLong(chrome_hwnd, GWL_EXSTYLE, ex)
        _SetWindowLong(chrome_hwnd, GWLP_HWNDPARENT, host_hwnd)  # set owner
        _user32.SetWindowPos(chrome_hwnd, None, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
        # Remove the button that was already created when Chrome first showed the
        # window (the style change alone doesn't make the taskbar re-evaluate).
        delete_taskbar_button(chrome_hwnd)
        return True
    except Exception:
        return False


def window_pid(hwnd: Optional[int]) -> Optional[int]:
    """The process id owning ``hwnd`` (Chrome's browser process) — used to force
    the window's whole process tree closed so detached Chrome never orphans."""
    if _user32 is None or not hwnd:
        return None
    try:
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value or None
    except Exception:
        return None


def host_metrics(host_hwnd: int) -> Optional[Tuple[int, int, int, int, float]]:
    """(origin_x, origin_y, client_w, client_h, dpi_scale) for the host window,
    all in PHYSICAL pixels (origin = client-area top-left in screen coords).
    Returns None if the window is minimized / not measurable — the caller treats
    that as 'hide the overlay'."""
    if _user32 is None or not host_hwnd:
        return None
    try:
        if _user32.IsIconic(host_hwnd):
            return None
        rect = wintypes.RECT()
        _user32.GetClientRect(host_hwnd, ctypes.byref(rect))
        cw, ch = rect.right, rect.bottom
        if cw <= 0 or ch <= 0:
            return None
        origin = wintypes.POINT(0, 0)
        _user32.ClientToScreen(host_hwnd, ctypes.byref(origin))
        scale = 1.0
        try:
            scale = _user32.GetDpiForWindow(host_hwnd) / 96.0
        except Exception:
            pass
        return origin.x, origin.y, cw, ch, scale or 1.0
    except Exception:
        return None


# ------------------------------------------------------------------- overlay
class BrowserOverlay:
    """Pins a Chrome window over a rectangle of a host window as an owned overlay.

    ``rect_provider()`` returns the target rectangle ``(x, y, w, h)`` in physical
    screen pixels, or ``None`` when the overlay should be hidden (host minimized,
    a modal dialog is covering the panel, etc.). It is polled on a tracker thread.
    """

    def __init__(self, chrome_hwnd: int, host_hwnd: int,
                 rect_provider: Callable[[], Optional[Tuple[int, int, int, int]]]):
        self._chrome = chrome_hwnd
        self._host = host_hwnd
        self._rect_provider = rect_provider
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last: Optional[Tuple[int, int, int, int]] = None
        self._hidden = False

    @property
    def chrome_hwnd(self) -> int:
        return self._chrome

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> bool:
        """Reframe Chrome as a frameless owned popup and begin tracking."""
        if _user32 is None or not self._chrome or not self._host:
            return False
        set_process_dpi_aware()
        # Frameless owned tool-window (driver_manager usually did this already the
        # moment the window appeared; reframe is idempotent). NOT a hide/show cycle:
        # hiding Chrome mid-load stalls the page ("stuck loading").
        reframe_as_owned(self._chrome, self._host)
        self._running = True
        self._thread = threading.Thread(target=self._track, name="browser-overlay", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop tracking. Leaves Chrome where it is (caller usually quits it)."""
        self._running = False

    def release_standalone(self) -> None:
        """Hand Chrome back as a normal, visible, standalone window — for the
        TYPE 2 'action required' handoff where the operator finishes manually."""
        self._running = False
        if _user32 is None or not self._chrome:
            return
        try:
            style = _GetWindowLong(self._chrome, GWL_STYLE)
            style &= ~WS_POPUP
            style |= WS_OVERLAPPEDWINDOW
            _SetWindowLong(self._chrome, GWL_STYLE, style)
            _SetWindowLong(self._chrome, GWLP_HWNDPARENT, 0)  # drop the owner
            # Re-place it on the visible desktop with a normal frame, and show it.
            _user32.SetWindowPos(self._chrome, HWND_TOP, 80, 60, 1200, 860,
                                 SWP_FRAMECHANGED | SWP_NOACTIVATE)
            _user32.ShowWindow(self._chrome, SW_SHOW)
        except Exception:
            pass

    # -- tracking -----------------------------------------------------------
    def _outer_rect(self):
        r = wintypes.RECT()
        _user32.GetWindowRect(self._chrome, ctypes.byref(r))
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)

    def _track(self) -> None:
        while self._running:
            try:
                rect = self._rect_provider()
                if rect is None:
                    if not self._hidden:
                        _user32.ShowWindow(self._chrome, SW_HIDE)
                        self._hidden = True
                else:
                    if self._hidden:
                        _user32.ShowWindow(self._chrome, SW_SHOWNA)
                        self._hidden = False
                    # Re-assert against Chrome's ACTUAL rect, not just the last
                    # target — so if anything resizes/maximizes Chrome (e.g. a
                    # maximize_window call or a fullscreen request) it snaps back
                    # into the panel within a tick. Un-maximize first; SetWindowPos
                    # alone won't resize a window stuck in the maximized state.
                    if _user32.IsZoomed(self._chrome):
                        _user32.ShowWindow(self._chrome, SW_RESTORE)
                    if self._outer_rect() != rect:
                        x, y, w, h = rect
                        _user32.SetWindowPos(self._chrome, HWND_TOP, x, y, w, h,
                                             SWP_NOACTIVATE)
            except Exception:
                pass
            time.sleep(0.01)
