"""桌面操作后端：协议、真实 PyAutoGUI 实现与测试用假后端。

对外符号：
- `DesktopBackend`：截图与键鼠契约。
- `DesktopPermissionError`：缺屏幕录制或辅助功能权限。
- `PyAutoGUIBackend`：生产实现。
- `FakeDesktopBackend`：记录调用、可注入失败的测试替身。
"""

from max_gui.desktop.backend import DesktopBackend, DesktopPermissionError
from max_gui.desktop.fake import FakeDesktopBackend
from max_gui.desktop.pyautogui_backend import PyAutoGUIBackend

__all__ = [
    "DesktopBackend",
    "DesktopPermissionError",
    "FakeDesktopBackend",
    "PyAutoGUIBackend",
]
