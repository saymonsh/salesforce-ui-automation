"""Win32 helpers to hide the off-screen automation Chrome window from the taskbar.

Issue #19's embedded live-preview panel is meant to be the *only* place the
operator sees the Selenium-driven Chrome. We keep Chrome **headed** (headless
breaks Salesforce Lightning's lazily-rendered DOM, and the org login policy
blocks headless logins) but parked off-screen, so the one remaining on-screen
remnant is its Windows taskbar button. These helpers strip that button
(``WS_EX_TOOLWINDOW``) so the window is fully invisible, and restore it for the
TYPE 2 'action required' handoff, when the operator has to finish a manual step
in the real browser.

Everything here is Windows-only and strictly best-effort: every failure is
swallowed so it can never break a run. On a non-Windows interpreter, or if the
window simply can't be located, the public functions are no-ops.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Optional, Set

try:
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
except Exception:  # pragma: no cover - non-Windows: helpers degrade to no-ops
    _user32 = None
    _kernel32 = None

# --- Win32 constants -------------------------------------------------------
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080  # not shown in the taskbar
WS_EX_APPWINDOW = 0x00040000   # forced into the taskbar
SW_HIDE = 0
SW_SHOWNA = 8  # show without activating (don't steal focus from our app)
GW_OWNER = 4
TH32CS_SNAPPROCESS = 0x00000002
_INVALID_HANDLE = ctypes.c_void_p(-1).value
_CHROME_WINDOW_CLASS = "Chrome_WidgetWin_1"

# GetWindowLongPtrW only exists on 64-bit; fall back to the 32-bit name.
if _user32 is not None:
    _GetWindowLong = getattr(_user32, "GetWindowLongPtrW", None) or _user32.GetWindowLongW
    _SetWindowLong = getattr(_user32, "SetWindowLongPtrW", None) or _user32.SetWindowLongW
    # Pin signatures so 64-bit handles/styles aren't truncated to 32-bit ints.
    _GetWindowLong.restype = ctypes.c_ssize_t
    _GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
    _SetWindowLong.restype = ctypes.c_ssize_t
    _SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _user32.GetWindow.restype = wintypes.HWND
    _user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetClassNameW.restype = ctypes.c_int
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.ShowWindow.restype = wintypes.BOOL
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL


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
    """PIDs of ``chrome.exe`` processes whose parent is ``parent_pid``.

    chromedriver spawns Chrome's **browser** process directly; that process owns
    the top-level window. (Renderer/GPU processes hang off the browser process
    and have no app window, so they're naturally excluded by the parent check.)
    Matching by process — rather than by window title or position — is what keeps
    us from grabbing one of the user's *own* Chrome windows.
    """
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


def _find_chrome_window(pids: Set[int]) -> Optional[int]:
    """First visible, top-level ``Chrome_WidgetWin_1`` window owned by one of
    ``pids`` — i.e. the automation browser's main window."""
    if _user32 is None or not pids:
        return None
    found = []

    def _cb(hwnd, _lparam):
        try:
            if not _user32.IsWindowVisible(hwnd):
                return True  # keep enumerating
            if _user32.GetWindow(hwnd, GW_OWNER):
                return True  # owned (popup/tooltip) — not the main window
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in pids:
                return True
            buf = ctypes.create_unicode_buffer(64)
            _user32.GetClassNameW(hwnd, buf, 64)
            if buf.value == _CHROME_WINDOW_CLASS:
                found.append(hwnd)
                return False  # stop enumerating
        except Exception:
            pass
        return True

    try:
        _user32.EnumWindows(_WNDENUMPROC(_cb), 0)
    except Exception:
        return None
    return found[0] if found else None


def _apply_taskbar_style(hwnd: int, *, show: bool) -> None:
    """Flip the window between tool-window (hidden) and app-window (visible in the
    taskbar). The style change only takes on the taskbar across a hide/show
    cycle, so we bracket it with ShowWindow — SW_SHOWNA reshows without stealing
    focus from our app (the window stays wherever it was, i.e. off-screen)."""
    ex = _GetWindowLong(hwnd, GWL_EXSTYLE)
    if show:
        ex = (ex & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
    else:
        ex = (ex & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
    _user32.ShowWindow(hwnd, SW_HIDE)
    _SetWindowLong(hwnd, GWL_EXSTYLE, ex)
    _user32.ShowWindow(hwnd, SW_SHOWNA)


def hide_chrome_taskbar_button(chromedriver_pid: int) -> Optional[int]:
    """Strip the automation Chrome window's taskbar button. Best-effort.

    Returns the located window handle so the caller can restore it later (or
    None if nothing was found / not on Windows).
    """
    if _user32 is None or not chromedriver_pid:
        return None
    try:
        hwnd = _find_chrome_window(_child_chrome_pids(chromedriver_pid))
        if hwnd:
            _apply_taskbar_style(hwnd, show=False)
        return hwnd
    except Exception:
        return None


def restore_chrome_taskbar_button(hwnd: Optional[int]) -> None:
    """Put the taskbar button back (TYPE 2 handoff). Best-effort no-op if hwnd is
    None or we're not on Windows."""
    if _user32 is None or not hwnd:
        return
    try:
        _apply_taskbar_style(hwnd, show=True)
    except Exception:
        pass
