"""基线任务的只读 macOS 前置检查与最小写入护栏。"""

from __future__ import annotations

import platform
from dataclasses import dataclass, field

from max_gui.baseline.models import BaselineStatus, BaselineTask, RiskLevel


@dataclass(slots=True)
class BaselineEnvironment:
    """检查平台和单轮写入预算；应用状态由人类确认与截图证据负责。"""

    allow_personal_write: bool = False
    written_tasks: set[str] = field(default_factory=set)

    def preflight(self, task: BaselineTask) -> tuple[BaselineStatus, str]:
        """检查平台和个人写入授权；不读取应用路径、账号、联系人或应用数据库。"""
        if platform.system() != "Darwin":
            return BaselineStatus.ENVIRONMENT_BLOCKED, "真实基线评测仅支持 macOS"
        if task.risk is RiskLevel.PERSONAL_WRITE and not self.allow_personal_write:
            return BaselineStatus.SAFETY_BLOCKED, "未确认个人写入任务"
        if task.id in self.written_tasks:
            return BaselineStatus.SAFETY_BLOCKED, "本轮该个人写入任务已执行，禁止重放"
        return BaselineStatus.READY, ""

    def mark_write(self, task: BaselineTask) -> None:
        """登记已进入个人写入任务，防止同轮自动重试或恢复重放。"""
        if task.risk is RiskLevel.PERSONAL_WRITE:
            self.written_tasks.add(task.id)
