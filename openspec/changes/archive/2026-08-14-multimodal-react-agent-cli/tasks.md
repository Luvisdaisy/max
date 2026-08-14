## 1. 项目骨架

- [x] 1.1 在 `pyproject.toml` 加入运行时依赖（`textual`、`langchain`、`langgraph`、`pillow`、`httpx`/`openai`、`pydantic`）以及可选/开发 extras；不引入 SQLite 或 `langgraph-checkpoint-sqlite`
- [x] 1.2 建立包布局：`cli.py`、`app.py`、`config.py`、`agent/`、`inference/`、`tools/`、`session/`、`widgets/`
- [x] 1.3 实现配置加载（vLLM `base_url`、模型别名 2B/4B/9B 且开发默认 `qwen3.5-2b`、权重根目录 `model/`、工作区根、`artifacts/sessions/`、最大迭代、图像限制、工具超时）
- [x] 1.4 将 `max-gui` 入口接到 CLI：`tui`（默认）、`serve`、`download`

## 2. 会话存储

- [x] 2.1 定义会话 JSON 结构（`id`/`title`/`model`/时间戳/`messages`，消息内容含文本与图像引用），统一写在 `artifacts/sessions/`，文件名用本地时间戳
- [x] 2.2 实现 store API：创建、列表、读取、更新标题/模型、追加消息、加载消息
- [x] 2.3 实现最近会话恢复、`--new` 强制新会话、加载时缺失图像占位
- [x] 2.4 为创建/恢复/切换以及缺失附件补充单元测试

## 3. 推理客户端

- [x] 3.1 实现面向已配置 `base_url`/`model` 的 OpenAI 兼容流式 chat 客户端
- [x] 3.2 实现 Pillow 预处理：类型检查、最长边缩放、最大字节重压缩、base64 `image_url` 部件
- [x] 3.3 将会话/LangGraph 消息（文本 + 图像 + 工具调用/结果）映射为 Chat Completions 载荷
- [x] 3.4 连接错误提示 `max-gui serve`；拒绝未知 `/model` 别名
- [x] 3.5 用伪造 SSE 端点测试流式、纯文本、多模态载荷

## 4. Agent 工具

- [x] 4.1 定义工具协议（名称、JSON schema、异步 invoke）与注册表
- [x] 4.2 实现限定工作区的 `read_file`、`write_file`、`list_dir`，拒绝路径逃逸
- [x] 4.3 实现 `search_files`（仅工作区内容搜索，返回路径 + 摘录）
- [x] 4.4 实现带超时的 `run_python` 子进程，cwd 为工作区，结果含 stdout/stderr/exit
- [x] 4.5 为 `write_file` 与 `run_python` 增加 TUI 确认门（会话可选择自动批准）
- [x] 4.6 未知工具返回错误字符串；补充沙箱与确认拒绝的单元测试

## 5. ReAct 图

- [x] 5.1 定义 LangGraph 状态（`session_id`、`messages`、`images`、`pending_tool_calls`、`iteration`、`status`）
- [x] 5.2 实现 `think`、`act`、`observe` 节点与循环边（无工具调用则结束）
- [x] 5.3 强制 `max_iterations`，并把迭代上限错误写入记录
- [x] 5.4 将检查点写入会话 JSON；实现中断 → `interrupted`，以及从检查点恢复（不使用 SQLite）
- [x] 5.5 通过 session store 持久化已完成/已中断的回合
- [x] 5.6 补充纯文本完成、一次工具循环、迭代上限、中断的测试

## 6. Textual REPL

- [x] 6.1 搭建 App 布局：记录、提示符（Enter 发送，Shift+Enter 换行）、状态/转圈
- [x] 6.2 在 worker 上提交非空回合；忽略空发送；运行期间 UI 保持可响应
- [x] 6.3 将 token 流式写入当前助手消息
- [x] 6.4 实现斜杠命令：`/new`、`/sessions`、`/attach`、`/model`、`/interrupt`、`/quit`
- [x] 6.5 实现 `/attach` 校验与待发送图像列表（终端支持时加上文件拖放）
- [x] 6.6 接上破坏性工具的确认提示；未知命令报错且不调用模型

## 7. 模型生命周期 CLI

- [x] 7.1 实现 `max-gui download [alias]`，经 ModelScope 下载到 `model/<alias>`（默认 2B；开发阶段权重已在 `model/qwen3.5-2b`）
- [x] 7.2 实现 `max-gui serve`，以 OpenAI 兼容模式启动 vLLM（max-model-len、gpu-memory-utilization、dtype）；开发默认加载 `model/qwen3.5-2b`
- [x] 7.3 权重缺失时，`serve`/`tui` 的模型调用失败并给出精确的 download 命令

## 8. 验收

- [x] 8.1 为 store、client、tools、graph 补充聚焦的单元/集成测试（不要求 GPU）
- [x] 8.2 手工过一遍：启动 TUI、发文本、附图像、跑一轮工具、中断、重启并恢复
- [x] 8.3 仅在需要时更新包描述/README，说明 `max-gui tui|serve|download` 用法

## 9. 链路修复

- [x] 9.1 拦截 TextArea Enter：Enter 发送，Shift+Enter 换行；用真实按键测试
- [x] 9.2 `max-gui serve` 按 `MAX_GUI_VLLM` / PATH / `~/.venv-vllm-metal/bin/vllm` 解析二进制，禁止回退到项目 `.venv`
- [x] 9.3 完整链路：假 SSE 覆盖 Enter→请求→会话 JSON；真服务探测 vLLM Metal + 最小 chat
