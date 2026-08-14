## 为什么

本地多模态模型已能在 Apple Silicon 上使用，但还没有一套把 Claude Code / Codex 风格 REPL、ReAct 循环、图像输入，以及 vLLM 上的 Qwen VL 推理合在一起的一等公民 CLI。当前 `max-gui` 仍是占位实现（`Hello from max-gui!`），没有 Agent、工具或 TUI。本变更锁定第一版产品形态，后续实现按此架构推进。

## 改什么

- 增加 Textual TUI REPL：输入、会话历史、token 级流式输出
- 增加 LangGraph ReAct Agent（Think → Act → Observe），支持中断恢复
- 接受文本与图像输入；预处理图像后，以 base64 或 URL 发给 OpenAI 兼容的 vLLM 接口
- 通过本地 vLLM 服务跑 Qwen 多模态模型；开发测试默认使用已下载的 Qwen3.5-2B（`model/qwen3.5-2b`），4B/9B 作为可切换别名
- 提供文件系统、本地搜索、沙箱代码执行、图像处理等 Function Calling 工具，并把结果写回上下文
- 将会话与历史保存为 `artifacts/sessions/` 下按时间戳命名的本地 JSON 文件，支持多会话恢复
- TUI 保持非阻塞：推理与工具在异步路径中运行

## 能力

### 新增能力

- `tui-repl`：Textual REPL — 提示符、历史、流式 token、斜杠命令、非阻塞界面
- `react-agent`：LangGraph ReAct 循环、状态、检查点、中断恢复
- `multimodal-inference`：vLLM OpenAI 兼容客户端、Qwen VL 模型配置、图像编码（base64/URL）
- `agent-tools`：统一 Function Calling 工具（文件、搜索、代码执行、图像）及结果回注
- `session-store`：基于本地 JSON 的会话/历史持久化与多会话恢复

### 修改的能力

- 无。`openspec/specs/` 尚无既有能力。

## 影响

- 包：`max-gui` 入口（`max_gui:main`）变为 TUI 启动器
- 在 `src/max_gui/` 下新增 TUI、Agent 图、工具、推理客户端、会话存储模块
- 新增运行时依赖：`textual`、`langchain`、`langgraph`、`pillow`、OpenAI 兼容 HTTP 客户端；ModelScope CLI 与 vLLM 仍为外部服务
- 新增本地数据：`artifacts/sessions/` 下的会话 JSON；模型权重已在仓库 `model/` 目录（开发默认 `qwen3.5-2b`）
- 目标运行时：macOS（Apple Silicon / Metal）上的 Python 3.12
