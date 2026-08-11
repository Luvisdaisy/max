"""桌面动作提议、审批与受控执行工具。"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Protocol

from pydantic import BaseModel, Field

from max_agent.orchestration.models import (
    ApprovedAction,
    DesktopAction,
    StandardObservation,
    action_hash,
)
from max_agent.tools.base import (
    ToolContext,
    ToolFailureCode,
    ToolPermission,
    ToolPhase,
    ToolReceipt,
)

ALLOWED_KEY_CHORDS = {
    ("ctrl", "end"),
    ("left",),
    ("right",),
    ("up",),
    ("down",),
    ("escape",),
    ("ctrl", "s"),
    ("alt", "f4"),
    ("enter",),
}


class RequestUserInput(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class RequestUserTool:
    name = "request_user"
    description = "Pause and ask the user for missing information or manual handling."
    permission = ToolPermission.USER
    allowed_phases = frozenset({ToolPhase.TOOL})
    timeout_seconds = 5.0
    recoverable = True
    model_visible = True
    side_effect = False
    input_model = RequestUserInput

    def invoke(
        self, tool_input: RequestUserInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        return ToolReceipt(
            tool_name=self.name, success=True, data={"question": tool_input.question}
        )


class DesktopActionProposalTool:
    """只向模型公开动作 schema；运行时在实际调用前截获并进入 Guard。"""

    name = "desktop_action"
    description = "Propose one atomic desktop action; runtime approval is mandatory."
    permission = ToolPermission.CONTROL
    allowed_phases = frozenset({ToolPhase.TOOL})
    timeout_seconds = 5.0
    recoverable = True
    model_visible = True
    side_effect = True
    input_model = DesktopAction

    def invoke(
        self, tool_input: DesktopAction, context: ToolContext | None = None
    ) -> ToolReceipt:
        return ToolReceipt.failure(
            self.name,
            ToolFailureCode.POLICY_DENIED,
            "desktop actions must pass through Guard",
        )


class GuardActionInput(BaseModel):
    action: DesktopAction
    observation: StandardObservation
    user_confirmed: bool = False
    ttl_seconds: float = Field(default=3.0, gt=0, le=10)


class GuardActionTool:
    name = "approve_action"
    description = "Validate and bind one action to the latest desktop observation."
    permission = ToolPermission.GUARD
    allowed_phases = frozenset({ToolPhase.GUARD})
    timeout_seconds = 5.0
    recoverable = True
    model_visible = False
    side_effect = False
    input_model = GuardActionInput

    def invoke(
        self, tool_input: GuardActionInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        action = tool_input.action
        observation = tool_input.observation
        if (
            action.kind == "key_chord"
            and tuple(key.lower() for key in action.keys or [])
            not in ALLOWED_KEY_CHORDS
        ):
            return ToolReceipt.failure(
                self.name, ToolFailureCode.POLICY_DENIED, "key chord is not allowed"
            )
        if action.window is not None:
            known = any(
                int(window.get("hwnd", 0)) == action.window.hwnd
                and int(window.get("process_id", 0)) == action.window.process_id
                and str(window.get("executable_path", "")).lower()
                == action.window.executable_path.lower()
                for window in observation.windows
            )
            foreground = observation.foreground_window
            if not known and (
                foreground is None
                or foreground.model_dump(exclude={"title"})
                != action.window.model_dump(exclude={"title"})
            ):
                return ToolReceipt.failure(
                    self.name,
                    ToolFailureCode.STALE_TARGET,
                    "target window is not in the latest observation",
                )
        target_bounds = observation.bounds
        if action.x is not None and action.y is not None:
            if action.window is not None:
                item = next(
                    (
                        window
                        for window in observation.windows
                        if int(window.get("hwnd", 0)) == action.window.hwnd
                    ),
                    None,
                )
                if item and item.get("bounds"):
                    from max_agent.orchestration.models import ScreenBounds

                    target_bounds = ScreenBounds.model_validate(item["bounds"])
            physical_x, physical_y = _physical_point(
                action.x,
                action.y,
                action.coordinate_space,
                target_bounds,
                observation.dpi,
            )
            if not target_bounds.contains(physical_x, physical_y):
                return ToolReceipt.failure(
                    self.name,
                    ToolFailureCode.POLICY_DENIED,
                    "coordinates are outside the approved target",
                )
        else:
            physical_x = physical_y = None
        high_impact = action.high_impact or _is_high_impact(action)
        if high_impact and not tool_input.user_confirmed:
            return ToolReceipt(
                tool_name=self.name,
                success=True,
                data={
                    "requires_user": True,
                    "question": "该动作可能保存、发送、删除或提交内容，是否允许执行？",
                    "action_hash": action_hash(action),
                    "state_fingerprint": observation.fingerprint,
                },
            )
        now = time.monotonic()
        resolved = action.model_copy(
            update={"x": physical_x, "y": physical_y, "coordinate_space": "physical"}
        )
        if (
            action.kind == "drag"
            and action.end_x is not None
            and action.end_y is not None
        ):
            end_x, end_y = _physical_point(
                action.end_x,
                action.end_y,
                action.coordinate_space,
                target_bounds,
                observation.dpi,
            )
            if not target_bounds.contains(end_x, end_y):
                return ToolReceipt.failure(
                    self.name,
                    ToolFailureCode.POLICY_DENIED,
                    "drag endpoint is outside the approved target",
                )
            resolved = resolved.model_copy(update={"end_x": end_x, "end_y": end_y})
        approved = ApprovedAction(
            action=resolved,
            action_hash=action_hash(action),
            state_fingerprint=observation.fingerprint,
            approved_at=now,
            expires_at=now + tool_input.ttl_seconds,
            physical_x=physical_x,
            physical_y=physical_y,
        )
        return ToolReceipt(
            tool_name=self.name, success=True, data={"approved": approved.model_dump()}
        )


class ExecuteActionInput(BaseModel):
    approved: ApprovedAction
    current_fingerprint: str


class DesktopAdapter(Protocol):
    def execute(self, action: DesktopAction) -> None: ...

    def foreground_identity(self) -> dict[str, object] | None: ...

    def release_all(self) -> None: ...


class ExecuteActionTool:
    name = "execute_action"
    description = "Execute one Guard-approved desktop action."
    permission = ToolPermission.CONTROL
    allowed_phases = frozenset({ToolPhase.ACTION})
    timeout_seconds = 15.0
    recoverable = True
    model_visible = False
    side_effect = True
    input_model = ExecuteActionInput

    def __init__(self, adapter: DesktopAdapter | None = None) -> None:
        self._adapter = adapter or PyAutoGuiDesktopAdapter()

    @property
    def adapter(self) -> DesktopAdapter:
        return self._adapter

    def invoke(
        self, tool_input: ExecuteActionInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        approved = tool_input.approved
        action = approved.action
        if (
            time.monotonic() > approved.expires_at
            or approved.state_fingerprint != tool_input.current_fingerprint
        ):
            return ToolReceipt.failure(
                self.name, ToolFailureCode.STALE_TARGET, "approval is stale"
            )
        if action.window is not None and action.kind != "activate_window":
            current = self._adapter.foreground_identity()
            expected = action.window.model_dump(exclude={"title"})
            actual = {key: current.get(key) for key in expected} if current else None
            if actual != expected:
                return ToolReceipt.failure(
                    self.name,
                    ToolFailureCode.STALE_TARGET,
                    "target window lost foreground focus",
                )
        try:
            self._adapter.execute(action)
        except Exception as error:
            self._adapter.release_all()
            return ToolReceipt.failure(
                self.name,
                ToolFailureCode.EXECUTION_FAILED,
                f"desktop action failed: {type(error).__name__}",
            )
        return ToolReceipt(
            tool_name=self.name,
            success=True,
            data={
                "action_hash": approved.action_hash,
                "executed_at": time.time(),
                "input_length": len(action.text) if action.text is not None else None,
            },
        )


class PyAutoGuiDesktopAdapter:
    """最小 Windows 输入适配器，不提供剪贴板、Shell 或文件能力。"""

    def execute(self, action: DesktopAction) -> None:
        import pyautogui

        pyautogui.FAILSAFE = True
        if action.kind == "activate_window":
            if action.window is None:
                raise RuntimeError("target window is required")
            # 任务栏中的窗口可能处于最小化状态；只置前不会恢复其有效边界，
            # 后续聚焦坐标可能被系统钳制到屏幕角落并触发 Fail-safe。
            ctypes.windll.user32.ShowWindow(action.window.hwnd, 9)
            if not ctypes.windll.user32.SetForegroundWindow(action.window.hwnd):
                raise RuntimeError("unable to activate target window")
        elif action.kind == "click":
            pyautogui.click(action.x, action.y)
        elif action.kind == "double_click":
            pyautogui.doubleClick(action.x, action.y)
        elif action.kind == "type_text":
            _type_unicode(action.text or "")
        elif action.kind == "scroll":
            pyautogui.scroll(action.amount or 0)
        elif action.kind == "drag":
            pyautogui.moveTo(action.x, action.y)
            pyautogui.dragTo(action.end_x, action.end_y, duration=0.2)
        elif action.kind == "key_chord":
            pyautogui.hotkey(*(action.keys or []))
        elif action.kind == "wait":
            time.sleep(action.seconds or 0)

    def foreground_identity(self) -> dict[str, object] | None:
        from max_agent.tools.perception.uia import foreground_window_identity

        return foreground_window_identity()

    def release_all(self) -> None:
        # Fail-safe 必须阻止新动作，但不能阻止终态释放；直接发送 key-up 和
        # mouse-up，避免光标位于角落时 PyAutoGUI 再次抛异常并遗留按下状态。
        user32 = ctypes.windll.user32
        for virtual_key in (0x11, 0x12, 0x10, 0x5B, 0x5C):
            user32.keybd_event(virtual_key, 0, 0x0002, 0)
        user32.mouse_event(0x0004 | 0x0010 | 0x0040, 0, 0, 0, 0)


_ULONG_PTR = (
    ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
)


class _MouseInput(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouse_data", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra_info", _ULONG_PTR),
    )


class _KeyboardInput(ctypes.Structure):
    _fields_ = (
        ("virtual_key", wintypes.WORD),
        ("scan_code", wintypes.WORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra_info", _ULONG_PTR),
    )


class _HardwareInput(ctypes.Structure):
    _fields_ = (
        ("message", wintypes.DWORD),
        ("parameter_low", wintypes.WORD),
        ("parameter_high", wintypes.WORD),
    )


class _InputPayload(ctypes.Union):
    _fields_ = (
        ("mouse", _MouseInput),
        ("keyboard", _KeyboardInput),
        ("hardware", _HardwareInput),
    )


class _Input(ctypes.Structure):
    _anonymous_ = ("payload",)
    _fields_ = (("type", wintypes.DWORD), ("payload", _InputPayload))


def _type_unicode(text: str) -> None:
    """通过 Unicode 键盘包输入文本，避免当前键盘布局或 IME 改写字符。"""
    inputs: list[_Input] = []
    for index, character in enumerate(text):
        if character in {"\r", "\n"}:
            # Notepad 需要标准 Return 虚拟键；连续 CRLF 只发送一次。
            if character == "\r" and text[index : index + 2] == "\r\n":
                continue
            inputs.extend(
                (
                    _Input(
                        type=1,
                        keyboard=_KeyboardInput(virtual_key=0x0D),
                    ),
                    _Input(
                        type=1,
                        keyboard=_KeyboardInput(virtual_key=0x0D, flags=0x0002),
                    ),
                )
            )
            continue
        # SendInput 的 Unicode 模式一次接收一个 UTF-16 码元，非 BMP 字符
        # 因而按代理对发送；不经剪贴板，也不受输入法状态影响。
        for unit in memoryview(character.encode("utf-16-le")).cast("H"):
            inputs.extend(
                (
                    _Input(
                        type=1,
                        keyboard=_KeyboardInput(scan_code=unit, flags=0x0004),
                    ),
                    _Input(
                        type=1,
                        keyboard=_KeyboardInput(scan_code=unit, flags=0x0004 | 0x0002),
                    ),
                )
            )
    if not inputs:
        return
    # Windows 11 记事本等现代控件可能丢弃一次性大批量 Unicode 包；按
    # down/up 对发送并留出极短消费间隔，仍不经过剪贴板或当前 IME。
    for offset in range(0, len(inputs), 2):
        pair = (_Input * 2)(*inputs[offset : offset + 2])
        sent = int(ctypes.windll.user32.SendInput(2, pair, ctypes.sizeof(_Input)))
        if sent != 2:
            raise RuntimeError("Unicode input was only partially sent")
        time.sleep(0.005)


def _is_high_impact(action: DesktopAction) -> bool:
    if action.kind == "key_chord":
        keys = tuple(key.lower() for key in action.keys or [])
        return keys in {("ctrl", "s"), ("alt", "f4"), ("enter",)}
    return False


def _physical_point(
    x: int,
    y: int,
    coordinate_space: str,
    bounds: object,
    dpi: int | None,
) -> tuple[int, int]:
    if coordinate_space == "normalized_1000":
        if not 0 <= x <= 1000 or not 0 <= y <= 1000:
            return -1, -1
        return (
            int(bounds.left + bounds.width * x / 1000),
            int(bounds.top + bounds.height * y / 1000),
        )
    if coordinate_space == "logical":
        scale = (dpi or 96) / 96
        return int(round(x * scale)), int(round(y * scale))
    return x, y
