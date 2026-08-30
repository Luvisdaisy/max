"""桌面状态层测试：快照时效、预期进度与平台未知状态。

所有用例只构造内存任务胶囊或 mock 平台信息，不读取真实窗口、不驱动键鼠。
"""

from __future__ import annotations

from max_gui.agent.context import (
    add_ui_candidates,
    new_task_context,
    register_expectation,
    replace_desktop_snapshot,
    verify_current_expectation,
)
from max_gui.desktop import observation


def _observation(*, dialog: str | None = None) -> dict[str, object]:
    """构造含 Chrome 前台窗口与可选弹窗的只读观察结果。"""
    return {
        "active_app": {"id": "chrome", "name": "Google Chrome", "role": "application"},
        "active_window": {"id": "17", "name": "报销系统", "role": "window"},
        "focused_element": {"id": None, "name": None, "role": None},
        "active_dialog": {"id": "file", "name": dialog, "role": "dialog"},
        "observation_status": "ok",
    }


def test_expectation_advances_progress_only_after_new_snapshot() -> None:
    """弹窗预期需动作后新帧确认，确认后才将关联进度标为已验证。"""
    context = new_task_context("上传报销单")
    context = replace_desktop_snapshot(
        context, frame_path="/tmp/before.png", observation=_observation()
    )
    context = register_expectation(
        context,
        {"kind": "dialog_appears", "target": "file picker", "progress_id": "open-picker"},
        source_frame_path="/tmp/before.png",
    )
    context = replace_desktop_snapshot(
        context,
        frame_path="/tmp/after.png",
        observation=_observation(dialog="File Picker"),
    )
    context = verify_current_expectation(context, previous_frame_path="/tmp/before.png")

    assert "current_expectation" not in context
    assert context["progress"] == [
        {"id": "open-picker", "label": "file picker", "status": "verified", "required": True}
    ]


def test_new_snapshot_does_not_reuse_old_ui_candidates() -> None:
    """新帧替换快照时清空上帧候选，避免历史控件参与下一步判断。"""
    context = new_task_context("上传文件")
    context = replace_desktop_snapshot(
        context, frame_path="/tmp/first.png", observation=_observation()
    )
    context = add_ui_candidates(
        context,
        frame_path="/tmp/first.png",
        candidates=[{"label": "Upload", "role": "button", "clickable": True}],
        source="locate",
    )
    context = replace_desktop_snapshot(
        context, frame_path="/tmp/second.png", observation=_observation()
    )

    assert context["desktop_snapshot"]["frame_path"] == "/tmp/second.png"
    assert context["desktop_snapshot"]["ui_elements"] == []


def test_non_macos_observation_is_explicitly_unknown(monkeypatch) -> None:
    """不支持的平台返回未知身份，不通过视觉或模型文本补造状态。"""
    monkeypatch.setattr(observation.platform, "system", lambda: "Linux")

    result = observation.observe_desktop_identity()

    assert result["observation_status"] == "unsupported_platform"
    assert result["active_app"]["name"] is None
    assert result["active_window"]["name"] is None
