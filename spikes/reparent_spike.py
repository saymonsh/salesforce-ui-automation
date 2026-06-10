r"""SetParent reparenting spike (idea C) — isolated, throwaway, self-contained.

Goal: answer the ONE make-or-break question for embedding the real automation
Chrome *inside* the Flet window via Win32 ``SetParent`` — does it render crisply
and do clicks land correctly on this machine's display scaling (high-DPI)? The
deep-research verdict rejected SetParent for the general case (airspace/clipping +
a cross-process DPI-awareness reset); our layout dodges the airspace problem, so
DPI is the only real unknown. This measures it without touching app code.

Self-contained on purpose: it inlines its own Chrome-window finder so it runs on
any branch (the app's win_window.py lives only on the feature branch).

What it does:
  1. Launches a real Selenium-driven Chrome (same as the app would).
  2. Opens a bare Flet window with the LEFT half reserved for the browser.
  3. Reparents Chrome's window into that left rectangle (strips its title bar,
     makes it a WS_CHILD of the Flet window) and tracks the rectangle on resize.

How to judge the result (this is the whole point):
  * Is the page text CRISP, or blurry/scaled wrong? (DPI test)
  * Click into the page and type — does the caret land where you click? (coord test)
  * Drag-resize the Flet window — does Chrome track the left half acceptably?
  * Navigate inside Chrome — does it survive?
If all good -> SetParent is viable; we commit and rip out the screencast.
If text is blurry or clicks miss -> fall back to idea A/B, nothing lost.

Run from the repo root:
    .venv\Scripts\python.exe -m spikes.reparent_spike
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes

import flet as ft
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

# --- DPI: align our process with Flutter (per-monitor-aware v2) so our Win32
# coordinate math is in the SAME physical-pixel space Flutter uses. Without this
# Windows virtualizes our coordinates and the child lands in the wrong spot —
# a false negative for the spike. Must run before any window is created.
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

HOST_TITLE = "REPARENT_SPIKE_HOST_7f3a"  # unique marker to find the Flet HWND
HEADER_PX = 8  # tiny top margin inside the client area

# --- Win32 constants -------------------------------------------------------
GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000
WS_OVERLAPPEDWINDOW = 0x00CF0000
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020
SWP_NOACTIVATE = 0x0010
HWND_TOP = 0
GWLP_HWNDPARENT = -8  # sets a top-level window's OWNER (not a child parent)
GW_OWNER = 4
TH32CS_SNAPPROCESS = 0x00000002
_INVALID_HANDLE = ctypes.c_void_p(-1).value
_CHROME_CLASS = "Chrome_WidgetWin_1"

# --- Win32 signatures (pin them so 64-bit handles/styles aren't truncated) ---
_GetLong = getattr(_user32, "GetWindowLongPtrW", None) or _user32.GetWindowLongW
_SetLong = getattr(_user32, "SetWindowLongPtrW", None) or _user32.SetWindowLongW
_GetLong.restype = ctypes.c_ssize_t
_GetLong.argtypes = [wintypes.HWND, ctypes.c_int]
_SetLong.restype = ctypes.c_ssize_t
_SetLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_user32.SetParent.restype = wintypes.HWND
_user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
_user32.GetWindow.restype = wintypes.HWND
_user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
_user32.MoveWindow.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int, wintypes.BOOL]
_user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.AttachThreadInput.restype = wintypes.BOOL
_user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
_user32.SetFocus.restype = wintypes.HWND
_user32.SetFocus.argtypes = [wintypes.HWND]
try:
    _user32.GetDpiForWindow.restype = wintypes.UINT
    _user32.GetDpiForWindow.argtypes = [wintypes.HWND]
except Exception:
    pass
_ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.EnumWindows.argtypes = [_ENUMPROC, wintypes.LPARAM]


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


# Shared between the embed thread and the UI-thread resize handler.
_state = {"host": None, "chrome": None}


def _child_chrome_pids(parent_pid: int):
    """PIDs of chrome.exe processes whose parent is the chromedriver PID — i.e.
    Chrome's browser process, which owns the top-level window."""
    pids = set()
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


def _find_chrome_window(pids):
    """First visible, top-level Chrome_WidgetWin_1 window owned by one of pids."""
    if not pids:
        return None
    found = []

    def _cb(hwnd, _l):
        try:
            if not _user32.IsWindowVisible(hwnd):
                return True
            if _user32.GetWindow(hwnd, GW_OWNER):
                return True
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in pids:
                return True
            buf = ctypes.create_unicode_buffer(64)
            _user32.GetClassNameW(hwnd, buf, 64)
            if buf.value == _CHROME_CLASS:
                found.append(hwnd)
                return False
        except Exception:
            pass
        return True

    _user32.EnumWindows(_ENUMPROC(_cb), 0)
    return found[0] if found else None


def _find_window_by_title(title: str):
    found = []

    def _cb(hwnd, _l):
        if not _user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        _user32.GetWindowTextW(hwnd, buf, 256)
        if buf.value == title:
            found.append(hwnd)
            return False
        return True

    _user32.EnumWindows(_ENUMPROC(_cb), 0)
    return found[0] if found else None


def _reposition():
    """Position the owned Chrome window over the left half of the host's client
    area. Chrome is a top-level (owned) window now, so we work in SCREEN coords:
    take the panel's top-left in the host's client space and map it to the
    screen with ClientToScreen."""
    host = _state["host"]
    chrome = _state["chrome"]
    if not host or not chrome:
        return
    rect = wintypes.RECT()
    _user32.GetClientRect(host, ctypes.byref(rect))
    cw, ch = rect.right, rect.bottom
    w, h = cw // 2, ch - HEADER_PX
    if w <= 0 or h <= 0:
        return
    origin = wintypes.POINT(0, HEADER_PX)
    _user32.ClientToScreen(host, ctypes.byref(origin))
    _user32.SetWindowPos(chrome, HWND_TOP, origin.x, origin.y, w, h,
                         SWP_NOACTIVATE)


def _track_loop():
    """Poll the host window's screen rect and re-place Chrome the instant it
    changes. Flet only surfaces a resize event on drag-RELEASE, so relying on it
    leaves Chrome lagging behind during the drag. A ~100Hz poll on a side thread
    reads the live rect (it updates throughout Windows' modal move/resize loop)
    and tracks smoothly — for moves too, not just resizes."""
    last = None
    while True:
        host = _state["host"]
        chrome = _state["chrome"]
        if host and chrome:
            r = wintypes.RECT()
            _user32.GetWindowRect(host, ctypes.byref(r))
            cur = (r.left, r.top, r.right, r.bottom)
            if cur != last:
                last = cur
                _reposition()
        time.sleep(0.01)


def _embed(chrome_hwnd, host_hwnd):
    """Make Chrome a frameless, OWNED top-level window pinned over the panel.

    Crucially NOT a WS_CHILD reparent: cross-process WS_CHILD reparenting breaks
    keyboard routing (Flutter reclaims focus; AttachThreadInput didn't fix it).
    An owned top-level window keeps Chrome's own native focus/keyboard handling
    intact, while the owner relationship (GWLP_HWNDPARENT) gives us the embedded
    feel: no taskbar button, minimizes/closes with the owner, always above it."""
    style = _GetLong(chrome_hwnd, GWL_STYLE)
    style &= ~(WS_CHILD | WS_OVERLAPPEDWINDOW | WS_CAPTION | WS_THICKFRAME
               | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)
    style |= WS_POPUP
    _SetLong(chrome_hwnd, GWL_STYLE, style)
    _SetLong(chrome_hwnd, GWLP_HWNDPARENT, host_hwnd)  # set owner
    _user32.SetWindowPos(chrome_hwnd, None, 0, 0, 0, 0,
                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
    _reposition()


def _launch_chrome():
    """Start a real Selenium Chrome and return (driver, chrome_hwnd)."""
    service = Service(r"C:\chromedriver\chromedriver.exe")
    opts = webdriver.ChromeOptions()
    opts.add_argument("--disable-backgrounding-occluded-windows")
    opts.add_argument("--disable-renderer-backgrounding")
    opts.add_argument("--disable-features=CalculateNativeWindowOcclusion")
    driver = webdriver.Chrome(service=service, options=opts)
    # Text-rich, interactive page so crispness + click-accuracy are easy to judge.
    # Swap for the real target if you want: welfareministry.lightning.force.com
    driver.get("https://www.google.com")
    driver_pid = service.process.pid
    chrome_hwnd = None
    for _ in range(40):  # ~10s for the window to appear
        chrome_hwnd = _find_chrome_window(_child_chrome_pids(driver_pid))
        if chrome_hwnd:
            break
        time.sleep(0.25)
    return driver, chrome_hwnd


def _embed_worker():
    """Wait for the Flet window to exist, then reparent Chrome into it."""
    host = None
    for _ in range(60):  # ~15s for the Flet window + its title
        host = _find_window_by_title(HOST_TITLE)
        if host:
            break
        time.sleep(0.25)
    chrome = _state["chrome"]
    if not host or not chrome:
        print(f"[spike] FAILED to locate windows (host={host}, chrome={chrome})")
        return
    _state["host"] = host
    dpi = 96
    try:
        dpi = _user32.GetDpiForWindow(host)
    except Exception:
        pass
    print(f"[spike] embedding chrome={chrome} into host={host} "
          f"(host DPI={dpi}, scale={dpi / 96:.2f}x)")
    _embed(chrome, host)
    threading.Thread(target=_track_loop, daemon=True).start()
    print("[spike] embedded. Judge: crisp text? clicks land? resize tracks?")


def main(page: ft.Page):
    page.title = HOST_TITLE
    page.padding = 0
    page.window.width = 1500
    page.window.height = 950
    page.bgcolor = ft.Colors.BLUE_GREY_900

    right = ft.Container(
        expand=True,
        padding=20,
        content=ft.Column(
            [
                ft.Text("SetParent spike", size=22, weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE),
                ft.Text("<- Chrome should be embedded in the left half.",
                        color=ft.Colors.WHITE70),
                ft.Divider(),
                ft.Text("Check:", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                ft.Text("- Is the text crisp (not blurry/mis-scaled)?  [DPI]",
                        color=ft.Colors.WHITE70),
                ft.Text("- Click + type in the page — caret where you click?  [coords]",
                        color=ft.Colors.WHITE70),
                ft.Text("- Drag-resize this window — does Chrome track?",
                        color=ft.Colors.WHITE70),
                ft.Container(height=12),
                ft.FilledButton("Re-sync rectangle", on_click=lambda e: _reposition()),
            ],
            spacing=8,
        ),
    )
    page.add(
        ft.Row(
            [
                ft.Container(width=page.window.width / 2),  # reserve the left half
                right,
            ],
            expand=True,
            spacing=0,
        )
    )

    # Keep the embedded child glued to the left half as the window moves/resizes.
    # Flet 0.84 funnels all window events through page.window.on_event.
    try:
        page.window.on_event = lambda e: _reposition()
    except Exception:
        pass

    threading.Thread(target=_embed_worker, daemon=True).start()


if __name__ == "__main__":
    print("[spike] launching Chrome…")
    _driver, _chrome_hwnd = _launch_chrome()
    if not _chrome_hwnd:
        print("[spike] could not find Chrome window — aborting.")
        try:
            _driver.quit()
        except Exception:
            pass
        sys.exit(1)
    _state["chrome"] = _chrome_hwnd
    print(f"[spike] chrome window = {_chrome_hwnd}; starting Flet host…")
    try:
        ft.app(target=main)
    finally:
        try:
            _driver.quit()
        except Exception:
            pass
