"""Read Unicode clipboard text without truncating Windows 64-bit handles."""
import ctypes
from ctypes import wintypes
import os


def windows_clipboard_sequence() -> int:
    """Identify a fresh clipboard write even when it copies the same text."""
    if os.name != 'nt':
        return 0
    try:
        getter = ctypes.windll.user32.GetClipboardSequenceNumber
        getter.argtypes = []
        getter.restype = wintypes.DWORD
        return int(getter())
    except Exception:
        return 0


def read_windows_clipboard() -> str:
    if os.name != 'nt':
        return ''
    try:
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
        kernel32.GlobalUnlock.restype = wintypes.BOOL
        if not user32.OpenClipboard(None):
            return ''
        try:
            handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
            if not handle:
                return ''
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                return ''
            try:
                return ctypes.wstring_at(pointer).strip()
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    except Exception:
        return ''
