"""单次运行 JSONL 记录器：增量刷新、恢复追加与故障降级。"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from max_gui.observability.events import RunEvent, RunEventType, new_run_id, safe_error_summary

RunEventCallback = Callable[[RunEvent], None]


class RunRecorder:
    """记录单次 Agent 运行并维护开发诊断汇总。

    初始化和写入错误不会抛入 Agent 主流程。发生一次磁盘错误后，本次运行停止后续
    磁盘写入，但事件仍通过内存回调交给 TUI。
    """

    def __init__(
        self,
        directory: Path,
        session_id: str,
        *,
        run_id: str | None = None,
        on_event: RunEventCallback | None = None,
    ) -> None:
        """创建或恢复记录器。

        参数：
            directory: `artifacts/runs/` 运行目录。
            session_id: 当前会话编号。
            run_id: 恢复时传入既有编号；缺省生成新编号。
            on_event: 每个事件产生后的轻量进程内回调。
        """
        self.directory = Path(directory)
        self.session_id = session_id
        self.run_id = run_id or new_run_id()
        self.path = self.directory / f"{self.run_id}.jsonl"
        self._on_event = on_event
        self._started = time.perf_counter()
        self._elapsed_offset_ms = 0
        self._sequence = 0
        self._handle: TextIO | None = None
        self._disk_enabled = True
        self._pending_failure: str | None = None
        self._needs_separator = False
        self._summary: dict[str, int] = {
            "model_calls": 0,
            "model_duration_ms": 0,
            "tool_calls": 0,
            "tool_duration_ms": 0,
            "tool_successes": 0,
            "tool_failures": 0,
            "iterations": 0,
        }
        self._usage: dict[str, int] | None = None
        self._open_tools: dict[str, str] = {}
        self._restore_existing()
        self._open_for_append()

    @property
    def disk_enabled(self) -> bool:
        """当前运行是否仍在写磁盘。"""
        return self._disk_enabled

    @property
    def unfinished_tools(self) -> dict[str, str]:
        """返回只有 started、尚无结束事件的工具调用副本。"""
        return dict(self._open_tools)

    def record(
        self,
        event_type: RunEventType,
        *,
        iteration: int = 0,
        subtask: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> RunEvent:
        """构造、追加并发布一条事件；磁盘故障时仍返回并回调事件。

        参数：
            event_type: 有限事件类型。
            iteration: 当前 ReAct 轮次。
            subtask: 当前子任务。
            data: 已去除大段敏感正文的载荷。

        返回：
            本次产生的 `RunEvent`。
        """
        event = self._build_event(event_type, iteration, subtask, data or {})
        self._update_summary(event)
        self._append(event)
        self._notify(event)
        self._publish_pending_failure(iteration=iteration, subtask=subtask)
        return event

    def summary(self, *, final_status: str | None = None) -> dict[str, Any]:
        """返回终态事件可直接使用的运行汇总副本。"""
        payload: dict[str, Any] = dict(self._summary)
        payload["duration_ms"] = self._elapsed_ms()
        if self._usage is not None:
            payload.update(self._usage)
        if final_status is not None:
            payload["final_status"] = final_status
        return payload

    def close(self) -> None:
        """刷新并关闭文件；关闭错误仅禁用磁盘记录。"""
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            handle.flush()
            handle.close()
        except OSError as exc:
            self._disable_disk(exc)

    def _build_event(
        self,
        event_type: RunEventType,
        iteration: int,
        subtask: str | None,
        data: dict[str, Any],
    ) -> RunEvent:
        """分配顺序号并构造公共信封。"""
        self._sequence += 1
        return RunEvent(
            event_id=f"{self.run_id}:{self._sequence}",
            sequence=self._sequence,
            timestamp=datetime.now().astimezone().isoformat(timespec="milliseconds"),
            elapsed_ms=self._elapsed_ms(),
            run_id=self.run_id,
            session_id=self.session_id,
            event_type=event_type,
            iteration=max(0, int(iteration)),
            subtask=subtask,
            data=dict(data),
        )

    def _restore_existing(self) -> None:
        """从既有合法行恢复顺序、汇总与未闭合工具，不改写坏行。"""
        if not self.path.is_file():
            return
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(raw, dict):
                        continue
                    sequence = raw.get("sequence")
                    if isinstance(sequence, int):
                        self._sequence = max(self._sequence, sequence)
                    self._elapsed_offset_ms = max(
                        self._elapsed_offset_ms,
                        _safe_int(raw.get("elapsed_ms")),
                    )
                    restored = _event_from_dict(raw)
                    if restored is not None:
                        self._update_summary(restored)
            with self.path.open("rb") as handle:
                handle.seek(0, 2)
                size = handle.tell()
                if size:
                    handle.seek(-1, 2)
                    self._needs_separator = handle.read(1) != b"\n"
        except OSError as exc:
            self._disable_disk(exc)

    def _open_for_append(self) -> None:
        """创建运行目录并以追加模式打开文件。"""
        if not self._disk_enabled:
            return
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("a", encoding="utf-8")
        except OSError as exc:
            self._disable_disk(exc)

    def _elapsed_ms(self) -> int:
        """返回包含恢复前偏移的单调累计耗时。"""
        return self._elapsed_offset_ms + int((time.perf_counter() - self._started) * 1000)

    def _append(self, event: RunEvent) -> None:
        """追加一行并 flush；失败后永久禁用本次磁盘写入。"""
        if not self._disk_enabled or self._handle is None:
            return
        try:
            if self._needs_separator:
                self._handle.write("\n")
                self._needs_separator = False
            self._handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
            self._handle.flush()
        except (OSError, TypeError, ValueError) as exc:
            self._disable_disk(exc)

    def _disable_disk(self, error: BaseException | str) -> None:
        """关闭失败句柄并缓存一次安全诊断。"""
        if not self._disk_enabled and self._pending_failure is not None:
            return
        self._disk_enabled = False
        self._pending_failure = safe_error_summary(error)
        handle = self._handle
        self._handle = None
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass

    def _publish_pending_failure(self, *, iteration: int, subtask: str | None) -> None:
        """把磁盘故障作为仅内存事件发布一次，避免递归写日志。"""
        detail = self._pending_failure
        if detail is None:
            return
        self._pending_failure = None
        event = self._build_event(
            "recorder.failed",
            iteration,
            subtask,
            {"message": "运行日志写入失败", "error": detail},
        )
        self._notify(event)

    def _notify(self, event: RunEvent) -> None:
        """隔离观察者异常，使 UI 故障不进入 Agent 控制流。"""
        if self._on_event is None:
            return
        try:
            self._on_event(event)
        except Exception:
            return

    def _update_summary(self, event: RunEvent) -> None:
        """按事件更新调用统计与未闭合工具表。"""
        self._summary["iterations"] = max(self._summary["iterations"], event.iteration)
        data = event.data
        if event.event_type == "model.started":
            self._summary["model_calls"] += 1
        elif event.event_type in {"model.completed", "model.failed"}:
            self._summary["model_duration_ms"] += _safe_int(data.get("duration_ms"))
            usage = usage_from_data(data)
            if usage is not None:
                if self._usage is None:
                    self._usage = {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                    }
                for key, value in usage.items():
                    self._usage[key] += value
        elif event.event_type == "tool.started":
            self._summary["tool_calls"] += 1
            call_id = str(data.get("call_id") or event.event_id)
            self._open_tools[call_id] = str(data.get("tool_name") or "")
        elif event.event_type in {"tool.completed", "tool.failed"}:
            self._summary["tool_duration_ms"] += _safe_int(data.get("duration_ms"))
            if event.event_type == "tool.completed":
                self._summary["tool_successes"] += 1
            else:
                self._summary["tool_failures"] += 1
            call_id = str(data.get("call_id") or "")
            self._open_tools.pop(call_id, None)


def usage_from_data(data: dict[str, Any]) -> dict[str, int] | None:
    """从事件载荷取出完整用量；缺输入或输出则视为未知，不把缺失当成 0。

    参数：
        data: 模型完成/失败或终态事件的 `data`。

    返回：
        含 `prompt_tokens`、`completion_tokens`、`total_tokens` 的字典；未知为 `None`。
    """
    prompt = _optional_nonneg_int(data.get("prompt_tokens"))
    completion = _optional_nonneg_int(data.get("completion_tokens"))
    if prompt is None or completion is None:
        return None
    total = _optional_nonneg_int(data.get("total_tokens"))
    if total is None:
        total = prompt + completion
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def _optional_nonneg_int(value: Any) -> int | None:
    """把用量字段收成非负整数；缺失或坏值返回 `None`。"""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number


def _safe_int(value: Any) -> int:
    """把统计字段收成非负整数，坏值视为零。"""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _event_from_dict(raw: dict[str, Any]) -> RunEvent | None:
    """从合法 JSON 对象恢复统计所需事件；结构不完整返回 `None`。"""
    try:
        event_type = str(raw["event_type"])
        if event_type not in _KNOWN_EVENT_TYPES:
            return None
        return RunEvent(
            schema_version=int(raw.get("schema_version") or 1),
            event_id=str(raw["event_id"]),
            sequence=int(raw["sequence"]),
            timestamp=str(raw["timestamp"]),
            elapsed_ms=int(raw.get("elapsed_ms") or 0),
            run_id=str(raw["run_id"]),
            session_id=str(raw["session_id"]),
            event_type=event_type,  # type: ignore[arg-type]
            iteration=int(raw.get("iteration") or 0),
            subtask=None if raw.get("subtask") is None else str(raw["subtask"]),
            data=dict(raw.get("data") or {}),
        )
    except (KeyError, TypeError, ValueError):
        return None


_KNOWN_EVENT_TYPES = {
    "run.started",
    "run.resumed",
    "run.completed",
    "run.failed",
    "run.interrupted",
    "state.changed",
    "model.started",
    "model.completed",
    "model.failed",
    "tool.started",
    "tool.completed",
    "tool.failed",
    "observation.completed",
    "recorder.failed",
}
