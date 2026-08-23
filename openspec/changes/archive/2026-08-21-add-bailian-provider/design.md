## Context

现有推理层仍是一个 `InferenceClient`：对 `Settings.base_url` 发流式 `/chat/completions`，`model` 为 `MODEL_NAME` 原文。`MAX_PROVIDER` 只有 `local` 与 `modelscope`。魔搭账号未绑定阿里云时 chat 返回 401，无法作为当前云端路径。

阿里云百炼 OpenAI 兼容接口：`Authorization: Bearer <API Key>`，`POST {base}/chat/completions`，支持 `stream`、`image_url`、`tools` / `tool_choice`，思考走 `reasoning_content`。华北 2（北京）专属域名为 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`。默认模型定为 `qwen3.8-27b`。

约束：不引入百炼 SDK、密钥不入库、OCR 仍本机、不新增 TUI `/provider`。

## Goals / Non-Goals

**Goals:**

- 第三条后端 `bailian`，与 `local` / `modelscope` 共用同一客户端、编码与 SSE 解析
- 北京专属域名 + 必填业务空间 ID；密钥仍用 `MAX_PROVIDER_KEY`
- 默认 `MODEL_NAME=qwen3.8-27b`；云端必须带 tools；缺密钥 / 缺 Workspace / 连接失败不得提示 `serve`
- `bailian` 把历史思考以 `reasoning_content` 回传

**Non-Goals:**

- 新加坡及其它地域、公共 `dashscope.aliyuncs.com` 回退
- `DASHSCOPE_API_KEY`、百炼 SDK、`--provider`、`/provider`
- `enable_search`、代码解释器、文档 / PPT、音视频输入、`enable_thinking` 等扩展字段
- 删除或改名 `modelscope`

## Decisions

### 1. 一个客户端，三套 Settings

`InferenceClient.stream` 的 payload 不变：`model`、`messages`、`stream`，有工具时加 `tools` 与 `tool_choice=auto`。不发 `extra_body`。`Settings.provider` 只改端点、密钥、权重检查与错误文案。

| | `local` | `modelscope` | `bailian` |
|---|---|---|---|
| 缺省 `MODEL_NAME` | `qwen3.5-4b` | `Qwen/Qwen3.8-27B` | `qwen3.8-27b` |
| `base_url` | `MAX_GUI_BASE_URL` 或本机 8000 | 固定魔搭 | `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` |
| `api_key` | `EMPTY` | `MAX_PROVIDER_KEY` | `MAX_PROVIDER_KEY` |
| 额外必填 | 完整本地权重 | 无 | `MAX_BAILIAN_WORKSPACE` |
| 权重 | 检查 | 不检查 | 不检查 |
| 连接失败 | 提示 `serve` | 提示网络 / Token | 提示网络 / Token / Workspace |

不引入 `BailianClient`。

备选：公共 `https://dashscope.aliyuncs.com/compatible-mode/v1`，免 Workspace。不采用：已选定北京专属域名。

### 2. 键名

- `MAX_PROVIDER`：`local` | `modelscope` | `bailian`，缺省 `local`
- `MAX_PROVIDER_KEY`：`modelscope` 与 `bailian` 必填；不认 `DASHSCOPE_API_KEY` / `MODELSCOPE_SDK_TOKEN`
- `MAX_BAILIAN_WORKSPACE`：仅 `bailian` 必填，去空白后非空；写入 `Settings` 并拼进 `base_url`
- `MODEL_NAME`：`bailian` 未写时为 `qwen3.8-27b`

`require_provider_key` 覆盖两个云端。另增 Workspace 校验（缺则中文错误，启动 TUI 或首次请求前失败）。`serve` 仍仅 `local`；`bailian` 与 `modelscope` 同样拒绝。

缺 Workspace 与缺密钥分成两条中文错误，避免把业务空间 ID 误写成「未设置 MAX_PROVIDER_KEY」。

### 3. bailian 回传思考

会话助手 content 已存 `text` 与可选 `reasoning`。当前 `to_chat_messages` 对助手只发 `content=text`，思考不进下一轮。

百炼 Qwen3.8 把思考放在 `reasoning_content`，且不得拼进 `content`。仅当 `provider=bailian` 且助手 content 含非空 `reasoning` 时，编码结果增加 `reasoning_content`，`content` 仍为正文。无思考则不加该字段。`local` / `modelscope` 行为不变。

不默认发送 `preserve_thinking` / `enable_thinking`，用服务端缺省。

### 4. HTTP 错误正文

沿用现有流式非 2xx 读 body 的路径，把百炼 JSON（如 401 说明）截断后展示。不为此改协议。

## Risks / Trade-offs

- [`qwen3.8-27b` 在百炼控制台的 Model Id 可能带前缀或大小写不同] → `MODEL_NAME` 可改；默认钉 `qwen3.8-27b`。真机 Id 不符则改 `.env`，必要时再改缺省。
- [专属域名拼错 Workspace 会连到错误主机] → 缺空校验；连接失败展示 `base_url`，不提示 `serve`。
- [部分模型拒绝未知的 `reasoning_content`] → 仅 `bailian` 且有历史思考时附加。
- [tools 与思考同时开时百炼行为与 vLLM 不完全一致] → 保持现有 SSE 拼装；失败走 HTTP/正文错误，不降级成正文 JSON。

## Migration Plan

1. 扩展 `PROVIDERS` 与 `load_settings`；`.env.example` 注释 `bailian`、Workspace、默认 `qwen3.8-27b`。
2. 客户端与 CLI 把 `bailian` 当云端：跳过权重、校验 key 与 Workspace、拒绝 serve。
3. `to_chat_messages` 按 provider 回传 `reasoning_content`。
4. 补配置、端点、缺 Workspace、思考回传、tools mock 测试。
5. 归档时再改 README。用户把 `MAX_PROVIDER` 改为 `bailian` 并填 key 与 Workspace 即可；旧会话无需迁移。

## Open Questions

无。默认模型已钉为 `qwen3.8-27b`，端点为北京专属域名。
