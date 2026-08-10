"""基于 Textual 的本地会话工作台，只负责输入、状态管理与安全展示。"""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic

from .console_core import (
    COMMAND_SPECS,
    ConsoleEvent,
    ConsoleEventKind,
    OperationResult,
    SessionStatus,
)


def create_textual_chat_app(
    dispatch,
    status_provider: Callable[[], SessionStatus] | None = None,
):
    """延迟导入 Textual 后创建聊天应用，保持非 UI 场景无需加载该依赖。"""
    from textual import events, work
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.timer import Timer
    from textual.widgets import Markdown, OptionList, Static, TextArea
    from textual.widgets.option_list import Option

    class Composer(TextArea):
        """把发送快捷键从 TextArea 的默认换行处理前交给应用仲裁。"""

        def __init__(self, key_handler, **kwargs) -> None:
            super().__init__(**kwargs)
            self._key_handler = key_handler

        async def _on_key(self, event: events.Key) -> None:
            """保留 Shift+Enter 换行，其余受控键由会话状态决定。

            TextArea 会在事件冒泡前消费可打印键和 Enter，因此这里必须在其
            内部插入处理之前拦截；普通编辑键仍完整委托给上游实现。
            """
            if event.key == "shift+enter":
                event.stop()
                event.prevent_default()
                self._replace_via_keyboard("\n", *self.selection)
                return
            if self._key_handler(event):
                event.stop()
                event.prevent_default()
                return
            await super()._on_key(event)

    class ChatApp(App[None]):
        """键盘优先的单请求终端会话，不持久化聊天或输入历史。"""

        TITLE = "MAX Local Agent"
        BINDINGS = [("ctrl+end", "latest", "返回最新内容")]
        CSS = """
        Screen {
            background: #0d1117;
            color: #d8dee9;
        }
        #topbar {
            dock: top;
            height: 3;
            padding: 1 2;
            background: #161b22;
            border-bottom: solid #30363d;
        }
        #brand {
            width: auto;
            margin-right: 2;
            color: #7ee787;
            text-style: bold;
        }
        #model-status {
            width: 1fr;
            color: #e6edf3;
        }
        #runtime-status {
            width: auto;
            margin-right: 2;
            color: #79c0ff;
        }
        #safety-status {
            width: auto;
            color: #8b949e;
        }
        #transcript {
            height: 1fr;
            padding: 1 2;
            overflow-x: hidden;
            scrollbar-size-vertical: 1;
        }
        .message {
            height: auto;
            margin-bottom: 1;
            padding: 1 2;
            background: #161b22;
        }
        .message-label {
            height: 1;
            margin-bottom: 1;
            text-style: bold;
        }
        .user-message {
            border-left: thick #58a6ff;
        }
        .assistant-message {
            border-left: thick #7ee787;
        }
        .command-message {
            border-left: thick #a5d6ff;
            color: #c9d1d9;
        }
        .tool-message {
            border-left: thick #d2a8ff;
            color: #d2a8ff;
        }
        .error-message {
            border-left: thick #ff7b72;
            color: #ffa198;
        }
        .notice-message {
            border-left: thick #8b949e;
            color: #8b949e;
        }
        #new-content {
            display: none;
            height: 1;
            padding: 0 2;
            background: #1f6feb;
            color: white;
            text-align: center;
        }
        #new-content.visible {
            display: block;
        }
        #command-menu {
            display: none;
            height: auto;
            max-height: 9;
            margin: 0 2;
            border: solid #30363d;
            background: #161b22;
        }
        #command-menu.visible {
            display: block;
        }
        #activity {
            height: 1;
            padding: 0 2;
            color: #8b949e;
        }
        #composer {
            height: 6;
            margin: 0 2;
            border: tall #30363d;
            background: #0d1117;
        }
        #composer:focus {
            border: tall #58a6ff;
        }
        #shortcuts {
            dock: bottom;
            height: 2;
            padding: 0 2;
            color: #8b949e;
            background: #161b22;
        }
        .compact #safety-status {
            display: none;
        }
        .compact #topbar {
            padding: 1;
        }
        .compact #transcript {
            padding: 0 1;
        }
        .compact #composer {
            height: 4;
            margin: 0 1;
        }
        .compact .message {
            padding: 0 1;
        }
        """

        def __init__(self) -> None:
            super().__init__()
            self._status_provider = status_provider or (
                lambda: SessionStatus("未知模型", "unloaded")
            )
            self._busy = False
            self._turn_id = 0
            self._started_at = 0.0
            self._stage = "本地会话就绪"
            self._activity_timer: Timer | None = None
            self._history: list[str] = []
            self._history_index = 0
            # 一个工具每轮至多调用一次；映射用于把 running 原位更新为最终状态。
            self._tool_widgets: dict[str, Static] = {}

        def compose(self) -> ComposeResult:
            """组合稳定的语义区域，便于窄终端布局与前端测试定位。"""
            yield Horizontal(
                Static("● MAX", id="brand", markup=False),
                Static("模型：加载中", id="model-status", markup=False),
                Static("unloaded", id="runtime-status", markup=False),
                Static("本地 · 只读", id="safety-status", markup=False),
                id="topbar",
            )
            yield VerticalScroll(self._welcome_widget(), id="transcript")
            yield Static(
                "有新内容 · Ctrl+End 返回最新",
                id="new-content",
                markup=False,
            )
            yield OptionList(id="command-menu", markup=False)
            yield Static("本地会话就绪", id="activity", markup=False)
            yield Composer(
                self._handle_composer_key,
                id="composer",
                placeholder="描述任务；输入 / 查看命令",
                soft_wrap=True,
                show_line_numbers=False,
                tab_behavior="focus",
            )
            yield Static(
                "Enter 发送 · Shift+Enter 换行 · Ctrl+↑/↓ 历史 · Ctrl+End 最新",
                id="shortcuts",
                markup=False,
            )

        def on_mount(self) -> None:
            """启动后立即呈现真实状态，并把键盘焦点放入编辑区。"""
            self._refresh_status_bar()
            self.query_one("#composer", TextArea).focus()

        def on_resize(self, event: events.Resize) -> None:
            """在窄终端隐藏次要安全文案，但保留模型和运行状态。"""
            self.set_class(event.size.width < 80, "compact")

        def on_text_area_changed(self, event: TextArea.Changed) -> None:
            """仅对单行斜杠前缀显示命令菜单，普通输入不受干扰。"""
            if event.text_area.id == "composer":
                self._update_command_menu(event.text_area.text)

        def on_option_list_option_selected(
            self, event: OptionList.OptionSelected
        ) -> None:
            """选择命令只完成输入，不隐式执行可能耗时的操作。"""
            command = event.option.id
            if command is None:
                return
            composer = self.query_one("#composer", TextArea)
            composer.load_text(f"{command} " if command == "/model" else command)
            composer.cursor_location = (0, len(composer.text))
            self._hide_command_menu()
            composer.focus()

        def _handle_composer_key(self, event: events.Key) -> bool:
            """统一仲裁菜单、发送和历史键；返回是否已经消费该按键。"""
            composer = self.query_one("#composer", TextArea)
            menu = self.query_one("#command-menu", OptionList)
            if menu.has_class("visible") and event.key in {"up", "down"}:
                if menu.option_count:
                    current = menu.highlighted if menu.highlighted is not None else 0
                    step = -1 if event.key == "up" else 1
                    menu.highlighted = (current + step) % menu.option_count
                return True
            if menu.has_class("visible") and event.key == "tab":
                if menu.highlighted is not None:
                    option = menu.get_option_at_index(menu.highlighted)
                    if option.id is not None:
                        composer.load_text(
                            f"{option.id} " if option.id == "/model" else option.id
                        )
                        composer.cursor_location = (0, len(composer.text))
                self._hide_command_menu()
                return True
            if event.key == "enter":
                self._submit_editor()
                return True
            if event.key == "ctrl+up":
                self._navigate_history(-1)
                return True
            if event.key == "ctrl+down":
                self._navigate_history(1)
                return True
            if event.key == "ctrl+end":
                self._scroll_to_latest()
                return True
            return False

        def action_latest(self) -> None:
            """允许焦点不在编辑区时也能通过快捷键返回最新内容。"""
            self._scroll_to_latest()

        def _submit_editor(self) -> None:
            """提交一条完整输入；忙碌门禁在启动 worker 前生效。"""
            composer = self.query_one("#composer", TextArea)
            value = composer.text
            if not value.strip():
                return
            if self._busy:
                self.notify("当前请求仍在运行。", severity="warning")
                return
            self._history.append(value)
            self._history_index = len(self._history)
            composer.load_text("")
            self._hide_command_menu()
            self._append_user_message(value)
            if value.lstrip().startswith("/"):
                self._render_result(dispatch(value))
                composer.focus()
                return
            self._begin_turn(value)

        def _begin_turn(self, value: str) -> None:
            """建立唯一活动 turn，并禁用编辑区直到结果安全返回。"""
            self._busy = True
            self._turn_id += 1
            self._started_at = monotonic()
            self._stage = "正在准备本地模型"
            composer = self.query_one("#composer", TextArea)
            composer.disabled = True
            self._activity_timer = self.set_interval(0.1, self._update_elapsed)
            self._update_elapsed()
            self.generate(value, self._turn_id)

        @work(thread=True, exit_on_error=False)
        def generate(self, value: str, turn_id: int) -> None:
            """在线程执行本地模型；所有 widget 变更经 UI 线程和 turn id 校验。"""
            try:
                result = dispatch(
                    value,
                    lambda event: self.call_from_thread(
                        self._render_progress, turn_id, event
                    ),
                )
            except Exception as error:  # UI 边界必须恢复，底层错误仍以本地文本呈现。
                result = OperationResult(
                    "runtime_error",
                    (
                        ConsoleEvent(
                            ConsoleEventKind.ERROR,
                            f"本地会话错误：{error}",
                        ),
                    ),
                )
            self.call_from_thread(self._finish_turn, turn_id, result)

        def _render_progress(self, turn_id: int, event: ConsoleEvent) -> None:
            """忽略过期 worker 回调，并原位更新阶段或工具状态。"""
            if not self._busy or turn_id != self._turn_id:
                return
            if event.kind == ConsoleEventKind.TOOL:
                self._render_tool_event(event)
                return
            if event.kind == ConsoleEventKind.NOTICE and event.state:
                self._stage = event.text
                self._update_elapsed()
                self._refresh_status_bar()

        def _finish_turn(self, turn_id: int, result: OperationResult) -> None:
            """只完成当前 turn 一次，并在成功与失败路径统一恢复编辑器。"""
            if not self._busy or turn_id != self._turn_id:
                return
            self._render_result(result)
            self._busy = False
            if self._activity_timer is not None:
                self._activity_timer.stop()
                self._activity_timer = None
            self._stage = "本地会话就绪"
            self.query_one("#activity", Static).update(self._stage)
            composer = self.query_one("#composer", TextArea)
            composer.disabled = False
            composer.focus()
            self._tool_widgets.clear()
            self._refresh_status_bar()

        def _update_elapsed(self) -> None:
            """使用单调时钟展示递增耗时，不参与业务结果或测试精确计时。"""
            if not self._busy:
                return
            elapsed = monotonic() - self._started_at
            self.query_one("#activity", Static).update(
                f"◌ {self._stage} · {elapsed:.1f}s"
            )

        def _render_result(self, result: OperationResult) -> None:
            """按事件类别渲染结果，并执行清屏或退出等显式 UI 语义。"""
            if result.kind == "clear":
                self._clear_transcript()
            else:
                for event in result.events:
                    self._append_event(event)
            self._refresh_status_bar()
            if result.should_exit:
                self.exit(result.exit_code)

        def _append_user_message(self, text: str) -> None:
            """用户输入始终按纯文本渲染，避免将内容解释为 Rich markup。"""
            self._mount_message(
                Vertical(
                    Static("› 用户", classes="message-label", markup=False),
                    Static(text, markup=False),
                    classes="message user-message",
                )
            )

        def _append_event(self, event: ConsoleEvent) -> None:
            """将结构化事件映射到角色明确且颜色非唯一的语义 widget。"""
            if event.kind == ConsoleEventKind.ASSISTANT:
                widget = Vertical(
                    Static("● MAX", classes="message-label", markup=False),
                    Markdown(event.text),
                    classes="message assistant-message",
                )
            else:
                labels = {
                    ConsoleEventKind.COMMAND: "◆ 命令",
                    ConsoleEventKind.ERROR: "! 错误",
                    ConsoleEventKind.NOTICE: "· 系统",
                }
                classes = {
                    ConsoleEventKind.COMMAND: "command-message",
                    ConsoleEventKind.ERROR: "error-message",
                    ConsoleEventKind.NOTICE: "notice-message",
                }
                widget = Vertical(
                    Static(
                        labels.get(event.kind, "· 系统"),
                        classes="message-label",
                        markup=False,
                    ),
                    Static(event.text, markup=False),
                    classes=f"message {classes.get(event.kind, 'notice-message')}",
                )
            self._mount_message(widget)

        def _render_tool_event(self, event: ConsoleEvent) -> None:
            """工具状态只组合白名单字段，并将完成状态更新到原始运行行。"""
            elapsed = event.elapsed_seconds or 0.0
            symbols = {"running": "◌", "succeeded": "✓", "failed": "!"}
            text = f"{symbols.get(event.state, '·')} {event.text} · {event.state} · {elapsed:.2f}s"
            existing = self._tool_widgets.get(event.text)
            if existing is not None:
                existing.update(text)
                return
            widget = Static(text, classes="message tool-message", markup=False)
            self._tool_widgets[event.text] = widget
            self._mount_message(widget)

        def _mount_message(self, widget) -> None:
            """统一挂载消息，并依据挂载前位置决定跟随或保留阅读视口。"""
            transcript = self.query_one("#transcript", VerticalScroll)
            follow_latest = transcript.is_vertical_scroll_end
            transcript.mount(widget)
            if follow_latest:
                self.call_after_refresh(transcript.scroll_end, animate=False)
                self.query_one("#new-content", Static).remove_class("visible")
            else:
                self.query_one("#new-content", Static).add_class("visible")

        def _clear_transcript(self) -> None:
            """清除可见记录并恢复不携带旧会话内容的欢迎状态。"""
            transcript = self.query_one("#transcript", VerticalScroll)
            transcript.remove_children()
            transcript.mount(self._welcome_widget())
            self.query_one("#new-content", Static).remove_class("visible")
            self.call_after_refresh(transcript.scroll_end, animate=False)

        def _welcome_widget(self):
            """创建可重复挂载的无状态欢迎提示。"""
            return Static(
                "MAX 已就绪。输入任务，或输入 / 查看本地命令。",
                classes="message notice-message",
                markup=False,
            )

        def _navigate_history(self, delta: int) -> None:
            """只在无未提交草稿时浏览进程内历史，避免覆盖用户编辑。"""
            composer = self.query_one("#composer", TextArea)
            if not self._history or (
                self._history_index == len(self._history) and composer.text
            ):
                return
            self._history_index = min(
                len(self._history), max(0, self._history_index + delta)
            )
            value = (
                ""
                if self._history_index == len(self._history)
                else self._history[self._history_index]
            )
            composer.load_text(value)
            lines = value.splitlines() or [""]
            composer.cursor_location = (len(lines) - 1, len(lines[-1]))

        def _update_command_menu(self, text: str) -> None:
            """按命令名称过滤补全；参数和多行内容不会误开菜单。"""
            menu = self.query_one("#command-menu", OptionList)
            if not text.startswith("/") or "\n" in text or " " in text:
                self._hide_command_menu()
                return
            matches = [item for item in COMMAND_SPECS if item.name.startswith(text)]
            if not matches:
                self._hide_command_menu()
                return
            menu.set_options(
                Option(f"{item.usage}  {item.description}", id=item.name)
                for item in matches
            )
            menu.highlighted = 0
            menu.add_class("visible")

        def _hide_command_menu(self) -> None:
            """隐藏并清空菜单，防止旧选项参与下一次键盘操作。"""
            menu = self.query_one("#command-menu", OptionList)
            menu.remove_class("visible")
            menu.clear_options()

        def _scroll_to_latest(self) -> None:
            """显式返回记录底部并清除新内容提示。"""
            self.query_one("#transcript", VerticalScroll).scroll_end(animate=False)
            self.query_one("#new-content", Static).remove_class("visible")

        def _refresh_status_bar(self) -> None:
            """从业务层只读快照刷新状态栏，避免前端直接操作运行时。"""
            snapshot = self._status_provider()
            self.query_one("#model-status", Static).update(
                f"模型：{snapshot.selected_model}"
            )
            self.query_one("#runtime-status", Static).update(snapshot.runtime_state)
            self.query_one("#safety-status", Static).update(snapshot.safety_boundary)

    return ChatApp()


def run_textual_chat(dispatch, status_provider=None) -> None:
    """创建并运行默认 Textual 会话工作台。"""
    create_textual_chat_app(dispatch, status_provider).run()
