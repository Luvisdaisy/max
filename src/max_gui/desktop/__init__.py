from max_gui.desktop.backend import DesktopBackend, DesktopPermissionError
from max_gui.desktop.fake import FakeDesktopBackend
from max_gui.desktop.pyautogui_backend import PyAutoGUIBackend

__all__ = [
    "DesktopBackend",
    "DesktopPermissionError",
    "FakeDesktopBackend",
    "PyAutoGUIBackend",
]
