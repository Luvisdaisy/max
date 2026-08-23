"""Textual REPL：会话历史、流式输出、斜杠命令与桌面/工作区确认。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, ClassVar

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Label, RichLog, Static

from max_gui.agent.graph import AgentRunner
from max_gui.config import MissingProviderKeyError, Settings, load_settings
from max_gui.inference.client import ConnectionFailedError, InferenceClient
from max_gui.inference.images import SUPPORTED_SUFFIXES, ImagePrepError
from max_gui.inference.ocr import shutdown_owned_ocr
from max_gui.inference.omniparser import shutdown_owned_locate
from max_gui.observability import RunEvent, usage_from_data
from max_gui.session.store import Session, SessionStore
from max_gui.tools.protocol import ConfirmationGate, ConfirmationScope
from max_gui.tools.registry import ToolRegistry, build_default_registry
from max_gui.widgets.prompt import PromptInput, PromptSubmitted

_STATUS_LABELS = {
    "thinking": "思考中…",
    "acting": "执行工具…",
    "observing": "观察中…",
    "done": "就绪",
    "interrupted": "已中断",
    "error": "错误",
}


class ConfirmScreen(ModalScreen[bool]):
    """模态确认：允许或拒绝即将执行的工具。"""

    def __init__(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """参数：`tool_name` 与最多预览前四个参数。"""
        super().__init__()
        self.tool_name = tool_name
        self.arguments = arguments

    def compose(self) -> ComposeResult:
        """渲染工具名、参数摘要与允许/拒绝按钮。"""
        preview = ", ".join(f"{key}={value!r}" for key, value in list(self.arguments.items())[:4])
        yield Vertical(
            Label(f"允许执行 {self.tool_name}？"),
            Label(preview or "(无参数)"),
            Horizontal(
                Button("允许", id="yes", variant="success"),
                Button("拒绝", id="no", variant="error"),
            ),
            id="confirm-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """「允许」关闭为 `True`，否则 `False`。"""
        self.dismiss(event.button.id == "yes")


class TuiConfirmationGate:
    """工具不再弹确认，一律放行。"""

    def __init__(self, app: MaxGuiApp) -> None:
        """参数：`app` 保留与原先装配方式兼容。"""
        self.app = app

    async def confirm(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        scope: ConfirmationScope = "workspace",
    ) -> bool:
        """忽略工具名、参数与范围，始终返回 `True`。"""
        return True


class MaxGuiApp(App[None]):
    """主界面：历史日志、流式助手区、待发送附件与多行输入。"""

    TITLE = "max-gui"
    CSS = """
    #record { height: 1fr; border: solid $accent; }
    #monitor { height: 8; border: solid $primary; padding: 0 1; color: $text-muted; }
    #transcript { height: 1fr; border: none; }
    #live { height: auto; max-height: 16; overflow-y: auto; display: none; padding: 0 1; }
    #prompt { height: 8; border: solid $primary; }
    #status { height: 3; color: $text-muted; }
    #pending { color: $warning; }
    #confirm-dialog { padding: 1 2; }
    """
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+c", "interrupt_or_quit", "中断/退出", show=False),
    ]

    def __init__(self, settings: Settings, *, force_new: bool = False) -> None:
        """参数：`force_new` 为真时不恢复最近会话。"""
        super().__init__()
        self.settings = settings
        self.force_new = force_new
        self.store = SessionStore(settings.sessions_dir)
        self.session: Session | None = None
        self.pending_images: list[Path] = []
        self.runner: AgentRunner | None = None
        self._turn_active = False
        self._stream_text = ""
        self._stream_reasoning = ""
        self._monitor: dict[str, Any] = {}
        self._monitor_recent: list[str] = []
        self._monitor_received_at = time.monotonic()
        self._reset_monitor()

    def compose(self) -> ComposeResult:
        """自上而下：标题、记录框（历史+实时流）、待附件、输入、状态、页脚。"""
        yield Header()
        with Vertical(id="record"):
            yield RichLog(id="transcript", highlight=True, markup=True, wrap=True)
            yield Static("", id="live", markup=False)
        yield Static("", id="monitor", markup=False)
        yield Static("", id="pending")
        yield PromptInput(id="prompt")
        yield Static("就绪", id="status")
        yield Footer()

    def on_mount(self) -> None:
        """打开或创建会话、重建 Runner，并渲染历史。"""
        self.session = self.store.open_or_create(
            model=self.settings.model_name, force_new=self.force_new
        )
        self._rebuild_runner()
        self.query_one(PromptInput).focus()
        self._render_session()
        self._refresh_monitor()
        self.set_interval(0.5, self._refresh_monitor_clock)
        self._set_status(f"会话 {self.session.id} · 模型 {self.settings.model_name}")

    def _rebuild_runner(self) -> None:
        """按当前设置重建工具表、推理客户端与 `AgentRunner`。"""
        gate: ConfirmationGate = TuiConfirmationGate(self)
        registry: ToolRegistry = build_default_registry(self.settings, gate=gate)
        client = InferenceClient(self.settings)
        self.runner = AgentRunner(self.settings, client, registry, self.store)

    def _log(self) -> RichLog:
        """历史记录控件。"""
        return self.query_one("#transcript", RichLog)

    def _set_status(self, text: str) -> None:
        """更新底部状态栏。"""
        self.query_one("#status", Static).update(text)

    def _refresh_pending(self) -> None:
        """刷新待发送附件文件名列表。"""
        if not self.pending_images:
            self.query_one("#pending", Static).update("")
            return
        names = ", ".join(path.name for path in self.pending_images)
        self.query_one("#pending", Static).update(f"待发送附件：{names}")

    def _render_session(self) -> None:
        """清空并重绘当前会话全部消息。"""
        log = self._log()
        log.clear()
        self._clear_live_stream()
        assert self.session is not None
        if not self.session.messages:
            log.write("[dim]新会话。输入文本发送，或使用 /attach /sessions。[/dim]")
            return
        for message in self.session.messages:
            self._write_message(message.role, message.content)

    def _write_message(self, role: str, content: dict[str, Any] | str) -> None:
        """按角色写入一条历史。图像缺失时标「缺失附件」。"""
        payload = content if isinstance(content, dict) else {"text": str(content)}
        text = str(payload.get("text") or "")
        images = payload.get("images") or []
        extras = []
        for image in images:
            if isinstance(image, dict) and image.get("missing"):
                extras.append("[缺失附件]")
            elif isinstance(image, dict):
                extras.append(f"[图 {Path(str(image.get('path'))).name}]")
        suffix = (" " + " ".join(extras)) if extras else ""
        if role == "user":
            self._log().write(f"[bold cyan]你[/bold cyan] {text}{suffix}")
        elif role == "tool":
            self._log().write(f"[magenta]工具[/magenta] {text[:400]}")
        else:
            reasoning = str(payload.get("reasoning") or "")
            if reasoning:
                self._log().write(f"[dim]思考[/dim] {reasoning}")
            if text or suffix or not reasoning:
                self._log().write(f"[bold green]助手[/bold green] {text}{suffix}")

    def on_prompt_submitted(self, event: PromptSubmitted) -> None:
        """清空输入框并在后台处理提交文本。"""
        text = event.text
        prompt = self.query_one(PromptInput)
        prompt.clear()
        self.run_worker(self._handle_submit(text), exclusive=False, group="turn")

    async def _handle_submit(self, raw: str) -> None:
        """斜杠走命令；空行忽略；回合进行中拒绝新输入。"""
        text = raw.strip()
        if text.startswith("/"):
            await self._handle_command(text)
            return
        if not text:
            return
        if self._turn_active:
            self._log().write("[yellow]上一回合仍在进行，请先 /interrupt[/yellow]")
            return
        await self._run_turn(text)

    async def _handle_command(self, raw: str) -> None:
        """分发 `/quit` `/new` `/sessions` `/attach` `/interrupt`。"""
        parts = raw.split(maxsplit=1)
        name = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        if name == "/quit":
            self.exit()
            return
        if name == "/new":
            assert self.session is not None
            self.session = self.store.create(model=self.settings.model_name)
            self.pending_images.clear()
            self._refresh_pending()
            self._render_session()
            self._set_status(f"新会话 {self.session.id}")
            return
        if name == "/sessions":
            await self._cmd_sessions(arg)
            return
        if name == "/attach":
            self._cmd_attach(arg)
            return
        if name == "/interrupt":
            if self.runner and self._turn_active:
                self.runner.interrupt()
                self._set_status("正在中断…")
            else:
                self._log().write("[dim]当前没有进行中的运行。[/dim]")
            return
        self._log().write(f"[red]未知命令：{name}[/red]")

    async def _cmd_sessions(self, arg: str) -> None:
        """无参数列出会话；有参数则切换到该编号。"""
        if arg:
            session = self.store.get(arg)
            if session is None:
                self._log().write(f"[red]找不到会话 {arg}[/red]")
                return
            self.session = session
            self._render_session()
            self._set_status(f"已切换到 {session.id}")
            return
        items = self.store.list()
        if not items:
            self._log().write("[dim]尚无会话。[/dim]")
            return
        lines = ["已存会话："]
        for item in items:
            marker = "*" if self.session and item.id == self.session.id else "-"
            lines.append(f"{marker} {item.id}  {item.title}  {item.updated_at}")
        self._log().write("\n".join(lines))

    def _cmd_attach(self, arg: str) -> None:
        """把本地图像加入下一回合附件队列。"""
        if not arg:
            self._log().write("[red]用法：/attach <路径>[/red]")
            return
        path = Path(arg).expanduser()
        if not path.is_file():
            self._log().write(f"[red]文件不存在：{arg}[/red]")
            return
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            self._log().write(f"[red]不支持的图像类型：{path.suffix}[/red]")
            return
        self.pending_images.append(path.resolve())
        self._refresh_pending()
        self._log().write(f"[dim]已附加 {path.name}[/dim]")

    async def _run_turn(self, text: str) -> None:
        """跑一轮 Agent，在记录框内流式更新，结束后写入历史并刷新会话。"""
        assert self.session is not None
        assert self.runner is not None
        images = [str(path) for path in self.pending_images]
        self.pending_images.clear()
        self._refresh_pending()
        self._write_message("user", {"text": text, "images": [{"path": path} for path in images]})
        self._turn_active = True
        self._set_status(_STATUS_LABELS["thinking"])
        saw_message = False

        def on_token(token: str) -> None:
            self.call_later(self._append_token, token)

        def on_reasoning(token: str) -> None:
            self.call_later(self._append_reasoning, token)

        def on_status(status: str) -> None:
            label = _STATUS_LABELS.get(status)
            if label:
                self.call_later(self._set_status, label)

        def on_message(role: str, content: dict[str, Any]) -> None:
            nonlocal saw_message
            saw_message = True
            self.call_later(self._commit_stream_message, role, content)

        def on_event(event: RunEvent) -> None:
            self.call_later(self._handle_run_event, event)

        try:
            resume = self.session.status == "interrupted" and not text
            state = await self.runner.run(
                self.session,
                user_text=text,
                image_paths=images,
                resume=resume,
                on_token=on_token,
                on_reasoning=on_reasoning,
                on_status=on_status,
                on_message=on_message,
                on_event=on_event,
            )
            if not saw_message:
                messages = state.get("messages") or []
                if messages:
                    last = messages[-1]
                    self._write_message(
                        str(last.get("role") or "assistant"), last.get("content") or {}
                    )
            status = str(state.get("status") or "done")
            if status == "error":
                self._set_status(str(state.get("error") or "错误"))
            elif status == "interrupted":
                self._set_status(_STATUS_LABELS["interrupted"])
            else:
                self._set_status(_STATUS_LABELS["done"])
        except MissingProviderKeyError as exc:
            self._log().write(f"[red]{exc}[/red]")
            self._set_status("缺少推理密钥")
        except ConnectionFailedError as exc:
            self._log().write(f"[red]{exc}[/red]")
            self._set_status("推理服务不可达")
        except ImagePrepError as exc:
            self._log().write(f"[red]{exc}[/red]")
            self._set_status("附件无效")
        except Exception as exc:
            self._log().write(f"[red]运行失败：{exc}[/red]")
            self._set_status("错误")
        finally:
            if not saw_message:
                self._flush_live_stream()
            self._turn_active = False
            self.session = self.store.get(self.session.id) or self.session

    def _reset_monitor(self) -> None:
        """把独立运行监控状态重置为默认可见的就绪摘要。"""
        self._monitor = {
            "run_id": "—",
            "status": "就绪",
            "iteration": 0,
            "subtask": "—",
            "activity": "—",
            "elapsed_ms": 0,
            "model_duration_ms": 0,
            "tool_duration_ms": 0,
            "tool_successes": 0,
            "tool_failures": 0,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "active": False,
            "diagnostic": "",
        }
        self._monitor_recent = []
        self._monitor_received_at = time.monotonic()

    def _handle_run_event(self, event: RunEvent) -> None:
        """消费一条安全事件摘要并刷新监控面板，不写入会话记录区。"""
        data = event.data
        if event.event_type == "run.started":
            self._reset_monitor()
            self._monitor.update(
                {
                    "run_id": event.run_id,
                    "status": "启动",
                    "active": True,
                }
            )
        elif event.event_type == "run.resumed":
            self._monitor.update(
                {
                    "run_id": event.run_id,
                    "status": "恢复",
                    "active": True,
                }
            )
            if data.get("unfinished_tools"):
                self._monitor["diagnostic"] = "上次工具结果未知，已等待重新观察"
        elif event.event_type == "state.changed":
            self._monitor["status"] = _monitor_status(str(data.get("to") or ""))
        elif event.event_type == "model.started":
            self._monitor["activity"] = f"模型 {(data.get('model') or '未知')!s}"
        elif event.event_type in {"model.completed", "model.failed"}:
            self._monitor["model_duration_ms"] += _nonnegative_int(data.get("duration_ms"))
            self._add_monitor_usage(data)
            self._monitor["activity"] = (
                "模型完成" if event.event_type.endswith("completed") else "模型失败"
            )
        elif event.event_type == "tool.started":
            self._monitor["activity"] = f"工具 {(data.get('tool_name') or '未知')!s}"
        elif event.event_type in {"tool.completed", "tool.failed"}:
            self._monitor["tool_duration_ms"] += _nonnegative_int(data.get("duration_ms"))
            if event.event_type == "tool.completed":
                self._monitor["tool_successes"] += 1
            else:
                self._monitor["tool_failures"] += 1
            self._monitor["activity"] = _event_summary(event)
        elif event.event_type == "observation.completed":
            self._monitor["activity"] = "观察完成"
        elif event.event_type in {"run.completed", "run.failed", "run.interrupted"}:
            self._monitor.update(
                {
                    "status": _monitor_status(str(data.get("final_status") or "")),
                    "model_duration_ms": _nonnegative_int(data.get("model_duration_ms")),
                    "tool_duration_ms": _nonnegative_int(data.get("tool_duration_ms")),
                    "tool_successes": _nonnegative_int(data.get("tool_successes")),
                    "tool_failures": _nonnegative_int(data.get("tool_failures")),
                    "activity": "—",
                    "active": False,
                }
            )
            self._replace_monitor_usage(data)
        elif event.event_type == "recorder.failed":
            self._monitor["diagnostic"] = "运行日志写入失败"

        self._monitor["run_id"] = event.run_id
        self._monitor["iteration"] = event.iteration
        self._monitor["subtask"] = event.subtask or "—"
        self._monitor["elapsed_ms"] = event.elapsed_ms
        self._monitor_received_at = time.monotonic()
        self._monitor_recent.append(_event_summary(event))
        self._monitor_recent = self._monitor_recent[-3:]
        self._refresh_monitor()

    def _add_monitor_usage(self, data: dict[str, Any]) -> None:
        """把一次已知模型用量累加到面板；未知则保持原累计。"""
        usage = usage_from_data(data)
        if usage is None:
            return
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            current = self._monitor.get(key)
            base = 0 if current is None else _nonnegative_int(current)
            self._monitor[key] = base + usage[key]

    def _replace_monitor_usage(self, data: dict[str, Any]) -> None:
        """用终态汇总覆盖面板用量，避免把同一运行再加一遍。"""
        usage = usage_from_data(data)
        if usage is None:
            self._monitor["prompt_tokens"] = None
            self._monitor["completion_tokens"] = None
            self._monitor["total_tokens"] = None
            return
        self._monitor.update(usage)

    def _refresh_monitor_clock(self) -> None:
        """活动运行期间推进显示耗时；不写事件也不修改持久化数据。"""
        if not self._monitor.get("active"):
            return
        self._refresh_monitor()

    def _refresh_monitor(self) -> None:
        """按当前安全摘要渲染默认可见的独立监控面板。"""
        try:
            monitor = self.query_one("#monitor", Static)
        except Exception:
            return
        elapsed_ms = _nonnegative_int(self._monitor.get("elapsed_ms"))
        if self._monitor.get("active"):
            elapsed_ms += int((time.monotonic() - self._monitor_received_at) * 1000)
        run_id = str(self._monitor.get("run_id") or "—")
        run_short = run_id if len(run_id) <= 18 else f"{run_id[:14]}…"
        recent = "｜".join(self._monitor_recent) or "暂无事件"
        diagnostic = str(self._monitor.get("diagnostic") or "")
        diagnostic_line = f"\n诊断：{diagnostic}" if diagnostic else ""
        monitor.update(
            "运行监控（本机）\n"
            f"任务：{run_short}  状态：{self._monitor['status']}  "
            f"轮次：{self._monitor['iteration']}/{self.settings.max_iterations}  "
            f"耗时：{elapsed_ms / 1000:.1f}s\n"
            f"子任务：{self._monitor['subtask']}  当前：{self._monitor['activity']}\n"
            f"模型：{self._monitor['model_duration_ms']}ms  "
            f"工具：{self._monitor['tool_duration_ms']}ms  "
            f"成功/失败：{self._monitor['tool_successes']}/{self._monitor['tool_failures']}\n"
            f"{_usage_line(self._monitor)}\n"
            f"最近：{recent}{diagnostic_line}"
        )

    def _live(self) -> Static:
        """流式助手文本控件。"""
        return self.query_one("#live", Static)

    def _clear_live_stream(self) -> None:
        """清空并隐藏流式区域。"""
        self._stream_text = ""
        self._stream_reasoning = ""
        live = self._live()
        live.update("")
        live.display = False

    def _refresh_live_stream(self) -> None:
        """把累计思考与正文画到 `#live`。"""
        live = self._live()
        if not self._stream_text and not self._stream_reasoning:
            live.update("")
            live.display = False
            return
        parts: list[tuple[str, str]] = []
        if self._stream_reasoning:
            parts.append(("思考 ", "dim italic"))
            parts.append((self._stream_reasoning, "dim"))
            if self._stream_text:
                parts.append(("\n", ""))
        if self._stream_text:
            parts.append(("助手 ", "bold green"))
            parts.append((self._stream_text, ""))
        live.update(Text.assemble(*parts))
        live.display = True

    def _flush_live_stream(self) -> None:
        """把当前 think 的流式内容落成一条历史并清空 `#live`。"""
        text = self._stream_text
        reasoning = self._stream_reasoning
        if text or reasoning:
            payload: dict[str, Any] = {"text": text}
            if reasoning:
                payload["reasoning"] = reasoning
            self._write_message("assistant", payload)
        self._clear_live_stream()

    def _append_token(self, token: str, started: bool | None = None) -> None:
        """在 UI 线程追加一个正文 token。`started` 保留给旧测试调用，无效果。"""
        _ = started
        self._stream_text += token
        self._refresh_live_stream()

    def _append_reasoning(self, token: str) -> None:
        """在 UI 线程追加一段思考增量。"""
        self._stream_reasoning += token
        self._refresh_live_stream()

    def _commit_stream_message(self, role: str, content: dict[str, Any]) -> None:
        """一次 think/act 提交后写入记录区。助手先 flush `#live`。"""
        payload = content if isinstance(content, dict) else {"text": str(content)}
        if role == "assistant":
            if self._stream_text or self._stream_reasoning:
                self._flush_live_stream()
            else:
                self._write_message("assistant", payload)
            self._clear_live_stream()
            return
        if self._stream_text or self._stream_reasoning:
            self._flush_live_stream()
        self._write_message(role, payload)

    def on_unmount(self) -> None:
        """退出时尽量停掉本进程拉起的 OCR 与 OmniParser 子进程。"""
        shutdown_owned_ocr()
        shutdown_owned_locate()

    def action_interrupt_or_quit(self) -> None:
        """Ctrl+C：回合中中断，否则退出。"""
        if self._turn_active and self.runner:
            self.runner.interrupt()
            return
        self.exit()

    def on_paste(self, event) -> None:
        """粘贴内容若是支持的图像路径，则加入附件而不写入输入框。"""
        text = getattr(event, "text", "") or ""
        path = Path(text.strip())
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            self.pending_images.append(path.resolve())
            self._refresh_pending()
            event.stop()


def _usage_line(monitor: dict[str, Any]) -> str:
    """把面板累计用量收成一行中文；没有任何已知用量时写未知，不用 0 表示缺失。"""
    usage = usage_from_data(monitor)
    if usage is None:
        return "用量：未知"
    return (
        f"用量：输入 {usage['prompt_tokens']} / 输出 {usage['completion_tokens']} "
        f"/ 合计 {usage['total_tokens']}"
    )


def _nonnegative_int(value: Any) -> int:
    """把监控统计字段收成非负整数，坏值视为零。"""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _monitor_status(status: str) -> str:
    """把内部状态映射为监控面板的短中文。"""
    return {
        "thinking": "思考中",
        "acting": "执行工具",
        "observing": "观察中",
        "done": "完成",
        "error": "错误",
        "interrupted": "已中断",
    }.get(status, status or "就绪")


def _event_summary(event: RunEvent) -> str:
    """生成不含 reasoning、键盘正文、OCR 全文和路径的安全事件摘要。"""
    data = event.data
    if event.event_type == "tool.started":
        return f"工具开始 {(data.get('tool_name') or '未知')!s}"
    if event.event_type in {"tool.completed", "tool.failed"}:
        result = "成功" if event.event_type == "tool.completed" else "失败"
        return (
            f"工具{result} {(data.get('tool_name') or '未知')!s} "
            f"{_nonnegative_int(data.get('duration_ms'))}ms"
        )
    if event.event_type == "model.started":
        return "模型开始"
    if event.event_type in {"model.completed", "model.failed"}:
        result = "完成" if event.event_type == "model.completed" else "失败"
        usage = usage_from_data(data)
        duration = f"{_nonnegative_int(data.get('duration_ms'))}ms"
        if usage is None:
            return f"模型{result} {duration} 用量未知"
        return (
            f"模型{result} {duration} 输入 {usage['prompt_tokens']} "
            f"输出 {usage['completion_tokens']}"
        )
    if event.event_type == "state.changed":
        return f"状态 {_monitor_status(str(data.get('to') or ''))}"
    if event.event_type == "observation.completed":
        return "观察完成"
    if event.event_type == "recorder.failed":
        return "运行日志写入失败"
    return {
        "run.started": "任务开始",
        "run.resumed": "任务恢复",
        "run.completed": "任务完成",
        "run.failed": "任务失败",
        "run.interrupted": "任务中断",
    }.get(event.event_type, event.event_type)


def run_app(settings: Settings | None = None, *, force_new: bool = False) -> None:
    """阻塞启动 Textual 应用。`settings` 缺省则 `load_settings()`。"""
    app = MaxGuiApp(settings or load_settings(), force_new=force_new)
    app.run()
