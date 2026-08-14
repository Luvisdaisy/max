## 背景

`max-gui` 是从零开始的 Python 3.12 包。当前入口只有 `max_gui:main`，打印一句问候。目标产品是 macOS 上的本地多模态 ReAct Agent CLI：Textual REPL、LangGraph Think/Act/Observe 循环、LangChain 风格工具、JSON 会话文件，以及独立进程中的 vLLM，通过 OpenAI 兼容 API 提供 Qwen VL。

约束：Apple Silicon / Metal、Python 3.12、本地优先（不强制云端 LLM）、推理与工具运行时 UI 必须保持可响应。

## 目标 / 非目标

**目标：**

- 交付可用的 Textual REPL：流式 token，接受文本与图像附件
- 运行带中断/恢复的 LangGraph ReAct 循环
- 对接本机 vLLM OpenAI 兼容端点（开发测试默认 Qwen3.5-2B；4B/9B 可切换）
- 提供文件系统、本地搜索、沙箱代码执行、图像预处理工具
- 将会话持久化为 `artifacts/sessions/` 下的 JSON，支持列表、切换、恢复

**非目标：**

- 云端模型供应商、多用户鉴权、Web UI
- 训练、微调，或图形化模型下载管理器（ModelScope CLI 为外部工具）
- 把 vLLM 嵌进 TUI 进程
- 本变更不做完整 OS 自动化、浏览器控制或插件市场
- Windows/Linux 不作为一等目标（先做 macOS）
- 不使用 SQLite 或任何嵌入式数据库保存会话

## 决策

### 1. 进程拆分：TUI + 外部 vLLM

TUI 进程不加载模型权重，只做异步 OpenAI 兼容客户端（`base_url`、`api_key`、`model`）。vLLM 作为独立服务运行（`max-gui serve` 或文档中的 `vllm serve`）。

`max-gui serve` 按顺序解析 vLLM 可执行文件：环境变量 `MAX_GUI_VLLM`、`PATH` 中的 `vllm`、默认 `~/.venv-vllm-metal/bin/vllm`。必须调用该二进制，不得回退到项目 `.venv` 的 `python -m vllm`。找不到则报中文错误并退出。

- 备选：进程内 Transformers/MLX、llama.cpp。本变更不采用：架构要求 vLLM PagedAttention / 连续批处理，以及 OpenAI 兼容表面。
- 取舍：vLLM 的 Metal/macOS 路径不如 CUDA 成熟。本机开发使用独立的 `~/.venv-vllm-metal`（vLLM 0.27.1 + metal 插件）。若 serve 启动失败，TUI 仍可启动，并展示带 serve 命令的连接错误。

### 2. 用 LangGraph StateGraph 做 ReAct

状态字段：`session_id`、`messages`、`images`、`pending_tool_calls`、`iteration`、`status`（`thinking` | `acting` | `observing` | `done` | `error` | `interrupted`）。

节点：`think`（模型调用，可流式）、`act`（分发工具）、`observe`（追加工具结果）。边循环直到模型不再返回工具调用、`iteration` 达到配置上限，或用户中断。

检查点：不使用 SQLite / `SqliteSaver`。将图状态写入对应会话 JSON（与消息同一文件），中断后从该快照恢复。

- 备选：在 TUI 里手写循环；只用 LangChain `AgentExecutor`。不采用：没有可持久化的图状态，中断也不干净。

### 3. Textual TUI，全异步

`max-gui` 启动 Textual 应用：记录、提示符、状态/转圈、斜杠命令。

- 用户输入与文件拖放入队；worker 调图，不阻塞事件循环
- 提示符覆盖 TextArea 的 Enter：Enter 发送，Shift+Enter 换行（不能依赖会被 TextArea 吞掉的 Binding）
- 流式 token 追加到当前助手消息
- 斜杠命令：`/new`、`/sessions`、`/attach`、`/model`、`/interrupt`、`/quit`
- 备选：prompt-toolkit 或 Rich Live。不采用：历史 + 流式 + 附件的控件模型更弱

### 4. 多模态载荷

图像用 Pillow 校验并缩放（最大边长 / 最大字节数来自配置），再作为 `image_url` 部件发送（`data:image/...;base64,...` 或 `file://` / http URL）。推理客户端把 LangGraph 消息映射到 OpenAI chat-completions 多模态 schema。

开发测试默认别名：`qwen3.5-2b`（本地目录 `model/qwen3.5-2b`，模型已下载）。`qwen2b` / `2b` 视为同一别名。4B、9B 只是配置别名，不是另一套代码路径。权重根目录为仓库内 `model/`，不是 `./models/`。

### 5. 通过 Function Calling 提供工具

工具实现统一协议（名称、JSON schema、异步 `invoke`）。第一批：

| 工具 | 行为 |
| --- | --- |
| `read_file` / `write_file` / `list_dir` | 仅允许工作区内路径 |
| `search_files` | 工作区内类似 ripgrep 的内容搜索 |
| `run_python` | 带超时的子进程，无网络，cwd = 工作区 |
| `prepare_image` | 模型调用前的缩放/编码辅助 |

工具结果作为 tool 消息追加，再送回 `think`。破坏性写入和 `run_python` 需要 TUI 内确认，除非该会话开启了自动批准。

### 6. 会话持久化（本地 JSON，不用 SQLite）

会话统一写在可配置目录，默认仓库内 `artifacts/sessions/`。每个会话一个 JSON 文件，文件名使用本地时间戳，例如 `20260814-153045.json`；会话 id 等于去掉扩展名的文件名。若同一秒冲突，追加 `-2`、`-3`。

每个文件至少包含：

- `id`、`title`、`model`、`created_at`、`updated_at`
- `messages`：角色 + JSON 内容（文本 + 图像引用）
- 可选：`status`、`auto_approve`、用于中断恢复的 `checkpoint`

启动时打开最近更新的会话，除非传入 `--new`。`/sessions` 列出并切换。不引入 SQLite、不使用 `~/.max-gui/sessions.db`。

### 7. 包布局

```
src/max_gui/
  __init__.py          # main() → TUI（或子命令）
  cli.py               # argparse：tui | serve | download
  app.py               # Textual App
  widgets/
  agent/               # 状态、图、节点
  inference/           # OpenAI 客户端、图像编码、模型配置
  tools/
  session/             # JSON 会话存储
  config.py
```

CLI 子命令：

- `max-gui` / `max-gui tui` — REPL
- `max-gui serve` — 解析独立 vLLM 二进制，用已配置的模型路径/长度/dtype/gpu-memory-utilization 启动；开发默认指向 `model/qwen3.5-2b`
- `max-gui download` — 用 ModelScope 下载到 `model/<alias>`（权重已在本地时，开发阶段主要走已有 `model/qwen3.5-2b`）

## 风险 / 取舍

- [vLLM 在 macOS/Metal 上性能可能不如 CUDA，或启动失败] → `serve` 隔离在 `max-gui serve`；TUI 降级为清晰离线错误；文档写明 2B/4B/9B 硬件下限
- [ReAct 循环失控] → 硬性 `max_iterations`；用户 `/interrupt`；持久化部分记录
- [代码执行与写文件] → 工作区沙箱、超时、破坏性工具需确认
- [大图撑爆上下文] → 编码前 Pillow 缩小 + 字节上限
- [并发写同一 JSON] → 仅 Agent worker 写会话文件；TUI 只通过 store API 读
- [4B/9B 权重可能未下完] → 开发默认锁定 2B；缺权重时给出对应的 `max-gui download` 命令

## 迁移计划

1. 加依赖与包布局；保持 `max-gui` 入口可用
2. 先做配置 + 针对 mock 或已运行 vLLM 的 OpenAI 客户端
3. JSON 会话存储，再图、再工具、再接 TUI
4. `download` / `serve` 放后，REPL 可对着任意 OpenAI 兼容 URL 开发

回滚：这是第一批功能；回退本变更后仍是占位问候入口。没有生产数据要迁移。本落地之后才会创建 `artifacts/sessions/`。

## 未决问题

- Qwen3.5-2B/4B/9B 在 ModelScope / Hugging Face 上的正式 ID（配置别名映射到本机 `model/<alias>`，待确认前以目录名为准）
- 目标 macOS 上官方 vLLM wheel 是否支持 MPS，或是否需要额外 index
- 默认工作区根：进程 cwd，还是显式 `--workspace`（默认：cwd）
- Web 搜索是否进 v1 工具（本设计不做 Web 搜索，只做本地 `search_files`）
