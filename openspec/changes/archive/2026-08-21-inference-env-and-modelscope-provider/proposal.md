## Why

第三周需要把大模型调用分成「本机 vLLM」和「魔搭 API-Inference」两条后端，但当前客户端无论 `base_url` 指到哪里都会检查本地权重，请求里的 `model` 也永远是目录别名。同时可调参数散落在 `MAX_GUI_*` 环境变量、CLI `--model` 和 TUI `/model` 里，短别名（`2b` / `qwen4b`）与完整目录名并存，云端 Model Id 无法表达。

## What Changes

- 用仓库根目录 `.env` 统一管理推理后端与现有可调字段；提交 `.env.example`，`.env` 不入库。启动时载入 `.env`，进程已有环境变量优先（测试可 monkeypatch）。
- 新增 `MAX_PROVIDER`（`local` | `modelscope`）、`MAX_PROVIDER_KEY`、`MODEL_NAME`。只认 `MAX_PROVIDER_KEY`，不认 `MODELSCOPE_SDK_TOKEN`。不引入 `--provider` 或其它新的 `--` 开关。
- **BREAKING**：去掉本地短别名映射（`2b` / `qwen2b` / `4b` / `qwen4b` / `9b` 等）。`MODEL_NAME` 在 `local` 下必须是完整目录名（如 `qwen3.5-4b`），在 `modelscope` 下必须是魔搭 Model Id。
- `local`（缺省）：默认 `MODEL_NAME=qwen3.5-4b`，检查 `model/<MODEL_NAME>` 权重，走本机 OpenAI 兼容端点，行为与现有 vLLM 客户端一致（含 tools）。
- `modelscope`：默认 `MODEL_NAME=Qwen/Qwen3.8-27B`，端点固定 `https://api-inference.modelscope.cn/v1`，不检查本地权重；缺 key 用中文报错，不得提示 `max-gui serve`。云端请求 MUST 携带与本地相同的 `tools` / `tool_choice=auto`，Agent 必须能走 function calling，不得降级成纯聊天或正文 JSON。
- 明确不做：API-Provider、Anthropic 兼容、Responses API、文生图、进程内 Transformers。
- **BREAKING**：删除 TUI `/model`。当前推理模型只来自 `.env` 的 `MODEL_NAME`。会话 JSON 的 `model` 仅作创建时盖章；`/sessions` 切换不改正在用的后端与模型。
- **BREAKING**：删除 CLI `max-gui download`、`--model`，以及 `download_model` / `MODELSCOPE_IDS`。缺权重时提示把权重放到 `model/<MODEL_NAME>`，不再给出 download 命令。`modelscope` 包若仅用于下载则移出依赖。
- `max-gui serve` 仅在 `MAX_PROVIDER=local` 时启动；`modelscope` 模式下拒绝并提示改 `.env`。保留 `max-gui` / `tui`、`serve`、`tui --new`。OCR 仍走本机独立服务，不跟 `MAX_PROVIDER`。

## Capabilities

### New Capabilities

- `runtime-config`：仓库根 `.env` 的载入顺序、键名、缺省值、示例文件与密钥不入库；可调字段的单一来源。

### Modified Capabilities

- `multimodal-inference`：双后端、完整 `MODEL_NAME`、云端 tools、删除 download / 短别名、缺权重与缺 key 的错误文案。
- `tui-repl`：斜杠命令不再包含 `/model`；启动不再用 `--model` 选模型。
- `session-store`：会话 `model` 字段不再驱动运行时模型切换。

## Impact

- 代码：`config.py`、`lifecycle.py`、`cli.py`、`inference/client.py`、`app.py`、测试与 README。
- 依赖：增加 `python-dotenv`；可能移除 `modelscope`。
- 破坏性：旧的短别名、`/model`、`max-gui download`、`--model`、`MAX_GUI_MODEL` / `MAX_GUI_API_KEY` 作为主配置键均不再作为对外接口（同名旧环境变量若仍出现，不保证兼容）。
- 不改：LangGraph ReAct 节点、桌面工具协议、OCR 端口、会话 JSON 文件布局。
