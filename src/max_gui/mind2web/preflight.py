"""Online-Mind2Web 的授权预检与运行时安全护栏。

本模块不访问网页内容；调用方可注入只读站点探针。运行时护栏只依据用户清单、当前 URL 和已解析的
桌面工具参数做决定，不能被模型提示绕过。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import urlparse

from max_gui.mind2web.models import (
    OnlineMind2WebTask,
    PreflightResult,
    PreflightStatus,
    SafetyManifest,
    SafetyRule,
)

_SENSITIVE_INPUT = re.compile(
    r"(?:password|passwd|cvv|cvc|card\s*number|social\s*security|身份证|银行卡|密码)", re.I
)
_HIGH_CONSEQUENCE = re.compile(
    r"(?:purchase|buy|checkout|pay|submit|publish|book|预约|购买|支付|发布|提交)", re.I
)


def plan_preflight(
    task: OnlineMind2WebTask,
    manifest: SafetyManifest,
    probe: Callable[[OnlineMind2WebTask], PreflightResult] | None = None,
) -> PreflightResult:
    """根据授权清单和可选只读探针产生执行前分类。

    参数：`task` 为候选题，`manifest` 为用户批准的边界，`probe` 可检查站点连通性或登录/CAPTCHA。
    返回：只有 `ready` 结果可进入真实浏览器。
    """
    rule = manifest.rule_for(task.task_id)
    if rule is None:
        return PreflightResult(
            task.task_id, PreflightStatus.UNSAFE_ACTION_RISK, "任务未列入安全清单"
        )
    if not is_allowed_url(task.website, rule):
        return PreflightResult(
            task.task_id,
            PreflightStatus.UNSAFE_ACTION_RISK,
            "任务起始域名不在允许范围内",
            task.website,
        )
    if _HIGH_CONSEQUENCE.search(task.instruction):
        return PreflightResult(
            task.task_id,
            PreflightStatus.UNSAFE_ACTION_RISK,
            "任务描述含高后果操作关键词",
            task.website,
        )
    result = (
        probe(task)
        if probe
        else PreflightResult(task.task_id, PreflightStatus.READY, url=task.website)
    )
    if result.task_id != task.task_id:
        raise ValueError("预检结果 task_id 与任务不一致")
    return result


def is_allowed_url(url: str, rule: SafetyRule) -> bool:
    """判断 URL 主机是否为清单允许域或其子域。

    参数：`url` 为待检查地址，`rule` 为当前任务规则。
    返回：主机符合允许域且协议为 HTTP(S) 时为真。
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return False
    return any(
        host == domain.lower() or host.endswith(f".{domain.lower()}")
        for domain in rule.allowed_domains
    )


class RuntimeSafetyGuard:
    """在每个桌面动作前执行的不可绕过安全检查。"""

    def __init__(
        self,
        rule: SafetyRule,
        current_url: Callable[[], str | None],
        on_block: Callable[[], None] | None = None,
    ) -> None:
        """保存当前题规则、只读 URL 获取函数和阻断后的中断回调。"""
        self.rule = rule
        self.current_url = current_url
        self._action_count = 0
        self.last_status: PreflightStatus | None = None
        self._on_block = on_block

    def __call__(self, tool_name: str, arguments: dict[str, object]) -> str | None:
        """返回阻断原因，或在动作符合边界时返回 `None`。

        键盘输入只有在清单白名单中才会放行；任何疑似敏感输入和高风险文本都会停止该题。
        """
        current = self.current_url()
        if current and not is_allowed_url(current, self.rule):
            self.last_status = PreflightStatus.UNSAFE_ACTION_RISK
            return self._block("当前页面已跳转到未授权域名，已停止后续动作")
        if current and re.search(r"(?:login|signin|captcha|verify)", current, re.I):
            self.last_status = PreflightStatus.CAPTCHA_OR_LOGIN
            return self._block("当前页面需要登录或 CAPTCHA，已停止该题")
        if tool_name in {
            "mouse_click",
            "mouse_scroll",
            "keyboard_type",
            "keyboard_press",
            "task_complete",
        }:
            if self._action_count >= self.rule.max_steps:
                self.last_status = PreflightStatus.UNSAFE_ACTION_RISK
                return self._block("已达到本题安全清单最大动作数")
            self._action_count += 1
        if tool_name == "keyboard_type":
            value = str(arguments.get("text") or "")
            if _SENSITIVE_INPUT.search(value):
                self.last_status = PreflightStatus.UNSAFE_ACTION_RISK
                return self._block("输入内容疑似包含敏感信息，已阻断")
            if _HIGH_CONSEQUENCE.search(value):
                self.last_status = PreflightStatus.UNSAFE_ACTION_RISK
                return self._block("输入内容可能触发高后果操作，已阻断")
            if value not in self.rule.allowed_type_values:
                self.last_status = PreflightStatus.UNSAFE_ACTION_RISK
                return self._block("输入内容不在本题安全清单白名单中，已阻断")
        if tool_name == "keyboard_press":
            keys = {str(key).lower() for key in arguments.get("keys", []) if isinstance(key, str)}
            if {"command", "l"}.issubset(keys) or {"ctrl", "l"}.issubset(keys):
                self.last_status = PreflightStatus.UNSAFE_ACTION_RISK
                return self._block("不允许通过地址栏导航到未审计页面")
        return None

    def _block(self, detail: str) -> str:
        """在阻断工具调用后请求 Agent 立即停止，避免后续推理循环。"""
        if self._on_block is not None:
            self._on_block()
        return detail
