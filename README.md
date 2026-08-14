# max-gui

本地多模态 ReAct GUI Agent CLI。开发测试默认使用已下载的 Qwen3.5-2B（`model/qwen3.5-2b`）。

当前能力：Textual REPL、LangGraph ReAct（Think / Act / Observe）、对接独立 vLLM 进程、工作区文件与沙箱 Python 工具。会话写在 `artifacts/sessions/`。操作系统级截图/键鼠尚未接入，调研见 [docs/gui-tools.md](docs/gui-tools.md)。

## 命令

```bash
uv sync --group dev
max-gui              # 启动 Textual REPL（默认）
max-gui tui --new    # 强制新会话
max-gui serve        # 启动 vLLM（默认加载 model/qwen3.5-2b）
max-gui download     # 下载默认 2B 到 model/qwen3.5-2b
max-gui download qwen3.5-4b
```

`max-gui serve` 会按顺序找 vLLM：`MAX_GUI_VLLM`、PATH 里的 `vllm`、`~/.venv-vllm-metal/bin/vllm`。未把该环境加入 PATH 时也能启动。Enter 发送，Shift+Enter 换行。

会话记录保存在 `artifacts/sessions/`，每个会话一个以时间戳命名的 JSON 文件。

## REPL 命令

- `/new` 新会话
- `/sessions` 列表；`/sessions <id>` 切换
- `/attach <路径>` 附加图像
- `/model [别名]` 查看或切换（`qwen3.5-2b` / `qwen2b` / `4b` / `9b`）
- `/interrupt` 中断当前运行
- `/quit` 退出
