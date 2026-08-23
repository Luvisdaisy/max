## Context

现有推理层是单一 OpenAI 兼容客户端：`InferenceClient` 对 `Settings.base_url` 发流式 `/chat/completions`，`model` 取自 `canonical_model`（经 `MODEL_ALIASES` 把 `2b` / `qwen4b` 等收成目录名），每次请求前 `require_weights()`。本地权重靠 `max-gui download`（ModelScope `snapshot_download`）和 `max-gui serve`（独立 vLLM）。TUI `/model` 与 CLI `--model` 可在运行时改别名。会话 JSON 的 `model` 在 `/sessions` 切换时会 `with_model` 写回 Settings。

魔搭 [API-Inference](https://www.modelscope.cn/docs/model-service/API-Inference/intro) 同样是 Chat Completions：`https://api-inference.modelscope.cn/v1`、Access Token、Model Id（如 `Qwen/Qwen3.8-27B`），视觉走 `image_url`。把 `MAX_GUI_BASE_URL` 指过去会失败：本地权重检查、错误文案仍叫 `serve`、发出去的 model 名魔搭不认。

约束：一个客户端、不引入厂商 SDK、密钥不入库、OCR 仍本机 8001。

## Goals / Non-Goals

**Goals:**

- `.env` 成为可调运行参数的单一来源（含 provider、key、模型名与既有 `MAX_GUI_*` 字段）
- `local` 与 `modelscope` 两条后端共用消息编码、流式思考/正文、tools
- 本地用完整目录名；云端用魔搭 Model Id；默认分别为 `qwen3.5-4b` 与 `Qwen/Qwen3.8-27B`
- 删除 `/model`、`--model`、`download`、短别名映射

**Non-Goals:**

- API-Provider、Anthropic 兼容接口、Responses API、AIGC 文生图
- 进程内 Transformers / MLX
- 在 TUI 里写回 `.env` 或新增 `/provider`
- 把 OCR 接到魔搭
- 兼容旧短别名或 `MAX_GUI_MODEL` / `MAX_GUI_API_KEY` 作为主键

## Decisions

### 1. 一个客户端，两套 Settings

`InferenceClient.stream` 仍发同一套 payload（`model`、`messages`、`stream`、有工具时 `tools` + `tool_choice=auto`）。`Settings.provider` 只改变：

| | `local` | `modelscope` |
|---|---|---|
| 缺省 `MODEL_NAME` | `qwen3.5-4b` | `Qwen/Qwen3.8-27B` |
| `base_url` | `.env` 的 `MAX_GUI_BASE_URL` 或 `http://127.0.0.1:8000/v1` | 固定 `https://api-inference.modelscope.cn/v1` |
| `api_key` | `EMPTY`（可空） | `MAX_PROVIDER_KEY`，缺则启动或首次 think 前失败 |
| 权重 | `model/<MODEL_NAME>` 必须完整 | 不检查 |
| 连接失败 | 提示 `max-gui serve` | 提示网络 / Token / 额度，禁止提 serve |

不引入 `VllmClient` / `ModelscopeClient` 类层次。

备选：官方 `openai` SDK 或 `modelscope` SDK。不采用：仓库已用 httpx 解析 SSE；云端协议相同。

### 2. `.env` 载入与键名

启动时 `detect_project_root()` 之后，若根目录存在 `.env`，用 `python-dotenv` 载入且 **`override=False`**（进程环境优先，pytest 可继续 monkeypatch）。无文件则用代码缺省。

对外键：

- `MAX_PROVIDER`：`local` | `modelscope`，缺省 `local`；其它值拒绝
- `MAX_PROVIDER_KEY`：仅 modelscope 必填
- `MODEL_NAME`：唯一模型字段。`local` 缺省 `qwen3.5-4b`；`modelscope` 未写时缺省 `Qwen/Qwen3.8-27B`
- 既有可调字段仍用 `MAX_GUI_*`（`BASE_URL`、`MAX_ITERATIONS`、图像上限、工具超时、vLLM 长度/显存/dtype、OCR、`WORKSPACE`）

`MAX_GUI_VLLM` / `MAX_GUI_ROOT` 仍是本机路径，不放进 `.env.example` 必填项。`.env` gitignore；提交 `.env.example`（无密钥）。不认 `MODELSCOPE_SDK_TOKEN`。

不新增 `--provider`。删除 CLI `--model`。保留 `tui --new` 与既有 `--workspace`（工作区仍可用环境或该开关，与本次模型选择无关）。

备选：把全部键改成 `MAX_*`。不采用：旧 `MAX_GUI_*` 已在规格与测试中，本次只新增三个键。

### 3. 一个 `MODEL_NAME`，取消短别名

删除 `MODEL_ALIASES`、`resolve_model_alias`。请求体 `model` 与本地目录名都是 `MODEL_NAME` 原文。

- `local`：合法当且仅当 `model/<MODEL_NAME>` 权重完整；未知名字不再靠白名单，缺目录就报路径
- `modelscope`：非空字符串原样发给魔搭；不映射到 `model/`

`max-gui serve` 仅 `provider=local`：用 `model/<MODEL_NAME>` 启动，`--served-model-name` 为该字符串。`provider=modelscope` 时 serve 以非零退出，中文说明改 `.env`。

不再提供 `max-gui download`。`MODELSCOPE_IDS`、`download_model` 删除。`modelscope` 依赖若无其它引用则移出 `pyproject.toml`。缺权重文案只报路径，例如「模型权重缺失：`model/qwen3.5-4b`」。

### 4. 云端必须 function calling

`think` 对两种 provider 都传入 `registry.schemas()`。客户端不得因 `modelscope` 省略 `tools`。若 HTTP 非 2xx 或流结束仍无正文/工具调用且服务报错，按现有错误通道展示。不实现「模型在正文里吐 JSON 再本地解析」的降级。

契约测试：mock 魔搭 SSE，含 `delta.tool_calls`，断言客户端拼出与本地相同的 `ChatDelta.tool_calls`。真机是否开通 tools 作为落地风险，不在设计里开第二协议。

### 5. 砍掉 `/model`；会话 `model` 只盖章

删除 `_cmd_model` 与帮助文案中的 `/model`。未知命令仍报错。

`Session.model` 在 `create` 时写入当时的 `MODEL_NAME`，供列表展示。`/sessions` 切换只换消息与记录区，**不得** `with_model(session.model)`。旧会话里若存过 `2b`，回放不管，运行时仍用 `.env`。

### 6. OCR 与密钥

OCR 继续本机 `MAX_GUI_OCR_*`。规划模型走魔搭时也不改 OCR。密钥只在环境 / `.env`，不写会话 JSON。

## Risks / Trade-offs

- [API-Inference 对 `tools` 支持不完整或与 vLLM 的 `tool_calls` 增量形状不同] → 客户端保持现有 SSE 拼装；加 mock 契约测试；真机失败则用户可见 HTTP/正文错误，不静默降级。若落地证实协议差，先改 OpenSpec 再改解析，而不是加 JSON 降级。
- [Qwen3.8-27B 或其它 Model Id 从 API-Inference 下架] → `MODEL_NAME` 可改；默认写在 `.env.example` 注释里。
- [魔搭额度 / 实名 / 单并发] → 文档说明；错误原文展示给用户。
- [`.env` 误提交密钥] → gitignore；example 留空 key。
- [用户仍调用 `max-gui download` 或 `/model`] → CLI 未知子命令 / TUI 未知命令，README 写明改 `.env`。
- [serve 时 `.env` 已是 modelscope + 27B Id] → serve 拒绝，避免把云端 Id 当成本地目录。

## Migration Plan

1. 增加 `python-dotenv`、`.env.example`、gitignore `.env`。
2. `load_settings` 先载入 `.env`，再读 `MAX_PROVIDER` / `MODEL_NAME` / `MAX_PROVIDER_KEY`。
3. 改客户端权重检查与错误文案；删别名、download、`--model`、`/model`。
4. 测试改为完整目录名（如 `qwen3.5-2b` 占位权重）；补 provider 与 mock tools 流。
5. 更新 README：复制 example、本地放权重、云端填 key。

无需数据迁移。旧会话文件可继续打开。

## Open Questions

无。探索阶段已钉死：云端默认 `Qwen/Qwen3.8-27B`、只认 `MAX_PROVIDER_KEY`、云端必须 tools、不做 API-Provider、一个 `MODEL_NAME`、砍 `/model` 与 download、本地完整名称。
