import ctypes
from ctypes import wintypes
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from core.clipboard import read_windows_clipboard


class ClipboardTests(unittest.TestCase):
    def test_unicode_text_and_full_width_handles(self):
        text = ctypes.create_unicode_buffer('  Liên kết video  ')
        handle = 0x100000001
        user32 = SimpleNamespace(OpenClipboard=Mock(return_value=True), CloseClipboard=Mock(),
                                 GetClipboardData=Mock(return_value=handle))
        kernel32 = SimpleNamespace(GlobalLock=Mock(return_value=ctypes.addressof(text)), GlobalUnlock=Mock())
        with patch('core.clipboard.os.name', 'nt'), patch('core.clipboard.ctypes.windll', SimpleNamespace(user32=user32,kernel32=kernel32), create=True):
            self.assertEqual(read_windows_clipboard(), 'Liên kết video')
        self.assertIs(user32.GetClipboardData.restype, wintypes.HANDLE)
        self.assertIs(kernel32.GlobalLock.restype, ctypes.c_void_p)
        kernel32.GlobalLock.assert_called_once_with(handle)
        kernel32.GlobalUnlock.assert_called_once_with(handle)
        user32.CloseClipboard.assert_called_once()

    def test_locked_clipboard_is_safe(self):
        user32 = SimpleNamespace(OpenClipboard=Mock(return_value=False), CloseClipboard=Mock(), GetClipboardData=Mock())
        kernel32 = SimpleNamespace(GlobalLock=Mock(), GlobalUnlock=Mock())
        with patch('core.clipboard.os.name', 'nt'), patch('core.clipboard.ctypes.windll', SimpleNamespace(user32=user32,kernel32=kernel32), create=True):
            self.assertEqual(read_windows_clipboard(), '')
        user32.GetClipboardData.assert_not_called()
        user32.CloseClipboard.assert_not_called()


if __name__ == '__main__':
    unittest.main()
