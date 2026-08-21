# max-gui

本地多模态 ReAct GUI Agent CLI。开发测试默认使用已下载的 Qwen3.5-4B（`model/qwen3.5-4b`）。仓库内 Python 代码需按 `AGENTS.md`「中文代码文档」在模块与函数签名处写中文说明。

当前能力：Textual REPL（思考与正文分区流式展示，工具结果在执行当时写入记录区，状态栏显示思考中 / 执行工具 / 观察中）、LangGraph ReAct（Think / Act / Observe；每次 think 注入中文 GUI 系统契约，不写入会话：标明真实操作系统，桌面任务一律键鼠完成，每一次键鼠动作都要截图核验；轻量计划字段；单回合默认最多 20 轮；think/act 增量写入会话；推理失败写入会话 `error`）、对接独立 vLLM 或魔搭 API-Inference（请求只编码最近一张仍存在的图；思考字段与正文分通道；两种后端都发送 tools）、工作区文件工具、PyAutoGUI 桌面工具（`screenshot` 图像回注，超界 `region` 夹紧到主屏；`screen_info`；`mouse_move` 成功后回注带光标的截图；`mouse_click` 只点当前位置、不接受坐标；`mouse_drag` 从当前位置拖到终点；`mouse_scroll`、`keyboard_type` / `keyboard_press`；坐标按模型看见的视图像素换算，必须落在当前视图内，出界拒绝；成功摘要只报视图像素；坐标系写入会话；点击/拖拽/滚轮/输入/按键成功后附新截图；工具不弹确认）。整图 `ocr` 与文字定位 `ocr_locate`（看不清字或需要可点框时调用，首次使用再启动独立 PaddleOCR-VL-1.5）。会话写在 `artifacts/sessions/`，截图写在 `artifacts/screenshots/`。助手消息可带思考原文 `reasoning`（回放用，不发给模型）。tool 消息会记下 `exec` 元数据，TUI 记录区只显示工具摘要文本。macOS 上拒绝 `windows` 键，提示改用 `command`；需开启屏幕录制与辅助功能。改本地 `MODEL_NAME` 后需重新执行 `max-gui serve`。

可调参数写在仓库根目录 `.env`（先复制 `.env.example`）。推理后端由 `MAX_PROVIDER` 选择：`local` 走本机 vLLM（默认 `MODEL_NAME=qwen3.5-4b`，权重放在 `model/<MODEL_NAME>`）；`modelscope` 走魔搭 API-Inference（默认 `Qwen/Qwen3.8-27B`），必须填写 `MAX_PROVIDER_KEY`。不要把填了密钥的 `.env` 提交进仓库。

## 命令

```bash
cp .env.example .env   # 按需填写 MAX_PROVIDER / MAX_PROVIDER_KEY / MODEL_NAME
uv sync --group dev
uv run ruff format src tests scripts   # 格式化
uv run ruff check src tests scripts    # 静态检查
uv run pytest                  # 测试
uv run python scripts/demo_week2_tools.py  # 第二周：打开计算器演示截图/键鼠/画框/OCR
max-gui              # 启动 Textual REPL（默认）
max-gui tui --new    # 强制新会话
max-gui serve        # 仅 local：启动 vLLM（默认加载 model/qwen3.5-4b）
```

`max-gui serve` 会按顺序找 vLLM：`MAX_GUI_VLLM`、PATH 里的 `vllm`、`~/.venv-vllm-metal/bin/vllm`。未把该环境加入 PATH 时也能启动。Enter 发送，Shift+Enter 换行。

会话记录保存在 `artifacts/sessions/`，每个会话一个以时间戳命名的 JSON 文件。当前推理模型只来自 `.env`，切换会话不会改模型。

## REPL 命令

- `/new` 新会话
- `/sessions` 列表；`/sessions <id>` 切换
- `/attach <路径>` 附加图像
- `/interrupt` 中断当前运行
- `/quit` 退出
