from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Label, RichLog, Static

from max_gui.agent.graph import AgentRunner
from max_gui.config import Settings, UnknownModelError, load_settings, resolve_model_alias
from max_gui.inference.client import ConnectionFailedError, InferenceClient
from max_gui.inference.images import ImagePrepError, SUPPORTED_SUFFIXES
from max_gui.session.store import Session, SessionStore
from max_gui.tools.protocol import ConfirmationGate
from max_gui.tools.registry import ToolRegistry, build_default_registry
from max_gui.widgets.prompt import PromptInput, PromptSubmitted


class ConfirmScreen(ModalScreen[bool]):
    def __init__(self, tool_name: str, arguments: dict[str, Any]) -> None:
        super().__init__()
        self.tool_name = tool_name
        self.arguments = arguments

    def compose(self) -> ComposeResult:
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
        self.dismiss(event.button.id == "yes")


class TuiConfirmationGate:
    def __init__(self, app: MaxGuiApp) -> None:
        self.app = app

    async def confirm(self, tool_name: str, arguments: dict[str, Any]) -> bool:
        if self.app.session and self.app.session.auto_approve:
            return True
        return bool(await self.app.push_screen_wait(ConfirmScreen(tool_name, dict(arguments))))


class MaxGuiApp(App[None]):
    TITLE = "max-gui"
    CSS = """
    #transcript { height: 1fr; border: solid $accent; }
    #prompt { height: 8; border: solid $primary; }
    #status { height: 3; color: $text-muted; }
    #pending { color: $warning; }
    #confirm-dialog { padding: 1 2; }
    """
    BINDINGS = [
        Binding("ctrl+c", "interrupt_or_quit", "中断/退出", show=False),
    ]

    def __init__(self, settings: Settings, *, force_new: bool = False) -> None:
        super().__init__()
        self.settings = settings
        self.force_new = force_new
        self.store = SessionStore(settings.sessions_dir)
        self.session: Session | None = None
        self.pending_images: list[Path] = []
        self.runner: AgentRunner | None = None
        self._turn_active = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="transcript", highlight=True, markup=True, wrap=True)
        yield Static("", id="pending")
        yield PromptInput(id="prompt")
        yield Static("就绪", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.session = self.store.open_or_create(model=self.settings.canonical_model, force_new=self.force_new)
        self.settings = self.settings.with_model(self.session.model)
        self._rebuild_runner()
        self.query_one(PromptInput).focus()
        self._render_session()
        self._set_status(f"会话 {self.session.id} · 模型 {self.settings.canonical_model}")

    def _rebuild_runner(self) -> None:
        gate: ConfirmationGate = TuiConfirmationGate(self)
        registry: ToolRegistry = build_default_registry(self.settings, gate=gate)
        client = InferenceClient(self.settings)
        self.runner = AgentRunner(self.settings, client, registry, self.store)

    def _log(self) -> RichLog:
        return self.query_one("#transcript", RichLog)

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    def _refresh_pending(self) -> None:
        if not self.pending_images:
            self.query_one("#pending", Static).update("")
            return
        names = ", ".join(path.name for path in self.pending_images)
        self.query_one("#pending", Static).update(f"待发送附件：{names}")

    def _render_session(self) -> None:
        log = self._log()
        log.clear()
        assert self.session is not None
        if not self.session.messages:
            log.write("[dim]新会话。输入文本发送，或使用 /attach /sessions /model。[/dim]")
            return
        for message in self.session.messages:
            self._write_message(message.role, message.content)

    def _write_message(self, role: str, content: dict[str, Any] | str) -> None:
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
            self._log().write(f"[bold green]助手[/bold green] {text}{suffix}")

    def on_prompt_submitted(self, event: PromptSubmitted) -> None:
        text = event.text
        prompt = self.query_one(PromptInput)
        prompt.clear()
        self.run_worker(self._handle_submit(text), exclusive=False, group="turn")

    async def _handle_submit(self, raw: str) -> None:
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
        parts = raw.split(maxsplit=1)
        name = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        if name == "/quit":
            self.exit()
            return
        if name == "/new":
            assert self.session is not None
            self.session = self.store.create(model=self.settings.canonical_model)
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
        if name == "/model":
            self._cmd_model(arg)
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
        if arg:
            session = self.store.get(arg)
            if session is None:
                self._log().write(f"[red]找不到会话 {arg}[/red]")
                return
            self.session = session
            self.settings = self.settings.with_model(session.model)
            self._rebuild_runner()
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

    def _cmd_model(self, arg: str) -> None:
        if not arg:
            self._log().write(f"当前模型：{self.settings.canonical_model}")
            return
        try:
            canonical = resolve_model_alias(arg)
        except UnknownModelError as exc:
            self._log().write(f"[red]{exc}[/red]")
            return
        self.settings = self.settings.with_model(canonical)
        if self.session:
            self.store.update(self.session, model=canonical)
        self._rebuild_runner()
        self._set_status(f"模型切换为 {canonical}")
        self._log().write(f"[dim]后续请求将使用 {canonical}[/dim]")

    async def _run_turn(self, text: str) -> None:
        assert self.session is not None
        assert self.runner is not None
        images = [str(path) for path in self.pending_images]
        self.pending_images.clear()
        self._refresh_pending()
        self._write_message("user", {"text": text, "images": [{"path": path} for path in images]})
        self._turn_active = True
        self._set_status("思考中…")
        assistant_started = False

        def on_token(token: str) -> None:
            nonlocal assistant_started
            started = assistant_started
            assistant_started = True
            self.call_later(self._append_token, token, started)

        try:
            resume = self.session.status == "interrupted" and not text
            state = await self.runner.run(
                self.session,
                user_text=text,
                image_paths=images,
                resume=resume,
                on_token=on_token,
            )
            if not assistant_started:
                messages = state.get("messages") or []
                if messages:
                    last = messages[-1]
                    self._write_message(str(last.get("role") or "assistant"), last.get("content") or {})
            status = str(state.get("status") or "done")
            if status == "error":
                self._set_status(str(state.get("error") or "错误"))
            elif status == "interrupted":
                self._set_status("已中断")
            else:
                self._set_status("就绪")
        except ConnectionFailedError as exc:
            self._log().write(f"[red]{exc}[/red]")
            self._set_status("推理服务不可达")
        except ImagePrepError as exc:
            self._log().write(f"[red]{exc}[/red]")
            self._set_status("附件无效")
        except Exception as exc:  # noqa: BLE001
            self._log().write(f"[red]运行失败：{exc}[/red]")
            self._set_status("错误")
        finally:
            self._turn_active = False
            self.session = self.store.get(self.session.id) or self.session

    def _append_token(self, token: str, started: bool) -> None:
        if not started:
            self._log().write(f"[bold green]助手[/bold green] {token}")
        else:
            self._log().write(token)

    def action_interrupt_or_quit(self) -> None:
        if self._turn_active and self.runner:
            self.runner.interrupt()
            return
        self.exit()

    def on_paste(self, event) -> None:  # noqa: ANN001
        text = getattr(event, "text", "") or ""
        path = Path(text.strip())
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            self.pending_images.append(path.resolve())
            self._refresh_pending()
            event.stop()


def run_app(settings: Settings | None = None, *, force_new: bool = False) -> None:
    app = MaxGuiApp(settings or load_settings(), force_new=force_new)
    app.run()
