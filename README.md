# max-gui

本地多模态 ReAct GUI Agent CLI。开发测试默认使用已下载的 Qwen3.5-4B（`model/qwen3.5-4b`）。仓库内 Python 代码需按 `AGENTS.md`「中文代码文档」在模块与函数签名处写中文说明。

当前能力：Textual REPL、LangGraph ReAct（Think / Act / Observe）、对接独立 vLLM 进程、工作区文件工具、PyAutoGUI 桌面工具（`screenshot` 图像回注、`screen_info`、`mouse_move` / `mouse_click` / `mouse_drag` / `mouse_scroll`、`keyboard_type` / `keyboard_press`；坐标按模型看见的视图像素换算，并写入会话）、整图 `ocr` 与文字定位 `ocr_locate`（看不清字或需要可点框时调用，首次使用再启动独立 PaddleOCR-VL-1.5）。会话写在 `artifacts/sessions/`，截图写在 `artifacts/screenshots/`。桌面点击、拖拽、滚动、输入、按键会单独确认，不受普通自动批准影响。macOS 需开启屏幕录制与辅助功能。改默认模型后需重新执行 `max-gui serve`。

## 命令

```bash
uv sync --group dev
uv run ruff format src tests scripts   # 格式化
uv run ruff check src tests scripts    # 静态检查
uv run pytest                  # 测试
uv run python scripts/demo_week2_tools.py  # 第二周：打开计算器演示截图/键鼠/画框/OCR
max-gui              # 启动 Textual REPL（默认）
max-gui tui --new    # 强制新会话
max-gui serve        # 启动 vLLM（默认加载 model/qwen3.5-4b）
max-gui download     # 下载默认 4B 到 model/qwen3.5-4b
max-gui download qwen3.5-2b
```

`max-gui serve` 会按顺序找 vLLM：`MAX_GUI_VLLM`、PATH 里的 `vllm`、`~/.venv-vllm-metal/bin/vllm`。未把该环境加入 PATH 时也能启动。Enter 发送，Shift+Enter 换行。

会话记录保存在 `artifacts/sessions/`，每个会话一个以时间戳命名的 JSON 文件。

## REPL 命令

- `/new` 新会话
- `/sessions` 列表；`/sessions <id>` 切换
- `/attach <路径>` 附加图像
- `/model [别名]` 查看或切换（默认 `qwen3.5-4b` / `4b`，亦可 `2b` / `9b`）
- `/interrupt` 中断当前运行
- `/quit` 退出
