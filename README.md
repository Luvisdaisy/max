# max-gui

本地多模态 ReAct GUI Agent CLI。开发测试默认使用已下载的 Qwen3.5-4B（`model/qwen3.5-4b`）。仓库内 Python 代码需按 `AGENTS.md`「中文代码文档」在模块与函数签名处写中文说明。

当前能力：Textual REPL（思考与正文分区流式展示，工具结果在执行当时写入记录区，状态栏显示思考中 / 执行工具 / 观察中；默认打开独立运行监控面板）、LangGraph ReAct（Think / Act / Observe；每次 think 注入中文 GUI 系统契约，不写入会话：标明真实操作系统，桌面任务一律键鼠完成，每一次键鼠动作都要截图核验；轻量计划字段；单回合默认最多 20 轮；think/act 增量写入会话；推理失败写入会话 `error`）、对接独立 vLLM、可信局域网 WSL 网关、魔搭 API-Inference、阿里云百炼 DashScope 或 OpenRouter（全部使用 OpenAI 兼容 Chat Completions；请求只编码最近一张仍存在的图；思考字段与正文分通道；五种后端都发送 tools；`dashscope` 把历史思考以 `reasoning_content` 回传；OpenRouter 默认模型为 `qwen/qwen3.5-plus`）、PyAutoGUI 桌面工具（`screenshot` 图像回注，超界 `region` 夹紧到主屏；`screen_info`；`mouse_move` 成功后回注带光标的截图；`mouse_click` 只点当前位置、不接受坐标；`mouse_drag` 从当前位置拖到终点；`mouse_scroll`、`keyboard_type` / `keyboard_press`；`keyboard_press.keys` 仅接受非空字符串数组；坐标按模型看见的视图像素换算，必须落在当前视图内，出界拒绝；成功摘要只报视图像素；坐标系写入会话；点击/拖拽/滚轮/输入/按键成功后附新截图；工具不弹确认）。整图 `ocr` 用于抄字；`locate` 首次调用再启动独立本机 OmniParser，对当前截图返回可执行的控件编号，历史或外部图片的检测结果仅供观察。会话写在 `artifacts/sessions/`，每次用户任务的结构化运行事件写在 `artifacts/runs/`，截图写在 `artifacts/screenshots/`。助手消息可带思考原文 `reasoning`（回放用；仅 `dashscope` 以独立字段回传）。tool 消息会记下 `exec` 元数据，TUI 记录区只显示工具摘要文本。macOS 上拒绝 `windows` 键，提示改用 `command`；需开启屏幕录制与辅助功能。调整本地模型定义后需重新执行 `max-gui serve`。

Agent 会在单个未完成任务内持久化有上限的已落地事实：仅复用绑定当前截图的有效定位编号与光标核验信息；新截图、失败或新任务会使过期事实失效。事实摘要不会保存逻辑坐标、OCR 原文或键盘输入正文。

可调参数写在仓库根目录 `.env`（先复制 `.env.example`）。推理后端由 `MAX_PROVIDER` 选择：`local` 走本机 vLLM；`remote` 走代码内定义的可信局域网 WSL 网关；`modelscope`、`dashscope` 与 `openrouter` 分别读取 `MAX_MODELSCOPE_KEY`、`MAX_DASHSCOPE_KEY` 与 `MAX_OPENROUTER_KEY`。可以同时保存全部云端密钥，切换时只改 `MAX_PROVIDER`。所有 provider 的模型、OpenAI 兼容根端点与能力统一定义在 `src/max_gui/provider.py`；不要把填了密钥的 `.env` 提交进仓库。

## 命令

```bash
cp .env.example .env   # 预先填写各云端密钥；切换时只改 MAX_PROVIDER
uv sync --group dev
uv run ruff format src tests scripts   # 格式化
uv run ruff check src tests scripts    # 静态检查
uv run pytest                  # 测试
uv run python scripts/demo_week2_tools.py  # 第二周：打开计算器演示截图/键鼠/画框/OCR
max-gui --benchmark     # 启动本地 Web GUI 评测首页，在页面选择运行 10 或 100 条任务
max-gui              # 启动 Textual REPL（默认）
max-gui tui --new    # 强制新会话
max-gui serve        # 仅 local：启动 vLLM（默认加载 model/qwen3.5-4b）
max-gui cleanup      # 直接清除截图、运行和会话记录
```

`max-gui serve` 会按顺序找 vLLM：`MAX_GUI_VLLM`、PATH 里的 `vllm`、`~/.venv-vllm-metal/bin/vllm`。未把该环境加入 PATH 时也能启动。Enter 发送，Shift+Enter 换行。

会话记录保存在 `artifacts/sessions/`，每个会话一个以时间戳命名的 JSON 文件。当前推理模型来自所选 provider 的 Python 定义，切换会话不会改模型。

## Web GUI 评测场

`artifacts/benchmarks/web-gui-v2.json` 显式定义 100 条本地 Web GUI 评测任务，不通过模板复制扩容。
任务按 easy、medium、hard 分层：easy 为 1 至 3 个主要可见操作，medium 为 5 至 6 个，hard 为 7 个
以上且至少跨越两个业务页面。评测首页保留「运行 10 条」和「运行 100 条」按钮；10 条是固定的跨难度、
跨能力冒烟集。每题从工作台统一启动，Agent 必须点击站内导航进入目标页面，地址栏直达不计入导航检查点。

评测场的可见页面由 Vue + Vite 构建，FastAPI 在单个仅监听 `127.0.0.1` 的进程中托管构建产物、业务
API 与受限的评测控制接口。首次运行或前端改动后，在 `frontend/benchmark-arena/` 执行 `npm install` 与
`npm run build`，再运行 `max-gui --benchmark`。Agent 只通过真实浏览器截图和键鼠操作工作台；重置和评分
状态接口不会显示在页面中。网站包含工作台、收件箱、项目、任务、日历、自动化、团队、报表和设置页面。
详情见 [`docs/web-gui-benchmark.md`](docs/web-gui-benchmark.md)。
运行中的评测可按 `Escape` 或点击「中断（Esc）」停止当前批次，已完成结果仍会写入报告。

## 本地运行日志与敏感信息

每次用户文本任务都有独立 `run_id`，事件按发生顺序追加到 `artifacts/runs/<run-id>.jsonl`。TUI 的独立运行监控面板默认打开，实时显示状态、轮次、子任务、当前模型或工具、累计耗时、成功/失败统计、token 用量（输入 / 输出 / 合计）和最近事件。用量来自推理接口回传的 `usage`；提供方未回传时面板显示「用量：未知」，不会把缺失写成 0。运行事件只服务本机开发排障，不启动监控网络端口，也不依赖外部日志或指标服务。

`artifacts/sessions/`、`artifacts/runs/` 与 `artifacts/screenshots/` 默认无限保留，应用不会按时间、数量或容量自动删除、轮转或压缩。需要清除时运行 `max-gui cleanup`，命令会直接执行且不读取交互输入。

这些本地产物可能包含用户消息、模型 reasoning、OCR 结果、键盘输入正文、文件路径与屏幕截图，禁止提交到 Git、公开打包或上传到不受信任的同步服务。运行 JSONL 不重复保存 reasoning、键盘输入正文、OCR 全文或截图字节，而是通过会话消息下标引用对应记录；这不改变会话 JSON 本身可能含敏感信息的事实。

## REPL 命令

- `/new` 新会话
- `/sessions` 列表；`/sessions <id>` 切换
- `/attach <路径>` 附加图像
- `/interrupt` 中断当前运行
- `/quit` 退出
