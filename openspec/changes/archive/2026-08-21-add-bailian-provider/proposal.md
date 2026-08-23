## Why

魔搭 API-Inference 当前会因账号未绑定阿里云而返回 401，无法作为 GUI Agent 的可用云端后端。阿里云百炼提供 OpenAI 兼容的 Chat Completions（含流式、视觉 `image_url`、function calling 与 `reasoning_content`），需要作为第三条推理后端接入，且不替换现有 `local` / `modelscope`。

## What Changes

- `MAX_PROVIDER` 增加 `bailian`。密钥仍只认 `MAX_PROVIDER_KEY`（百炼 API Key），不认 `DASHSCOPE_API_KEY`。
- 新增必填 `MAX_BAILIAN_WORKSPACE`（业务空间 ID）。`bailian` 的端点固定为华北 2（北京）专属域名：`https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`。本次不实现新加坡等其它地域，也不回退到 `dashscope.aliyuncs.com`。
- `bailian` 未设置 `MODEL_NAME` 时默认为 `qwen3.8-27b`。请求 `model` 仍为 `MODEL_NAME` 原文。不检查本地权重。
- 与其它云端一样：必须带 `tools` / `tool_choice=auto`；连接失败或缺密钥/缺 Workspace 用中文报错，不得提示 `max-gui serve`。`max-gui serve` 在 `bailian` 下拒绝。
- Qwen3.8 思考内容走 `reasoning_content`。`bailian` 编码助手消息时 MUST 把会话里已存的 `reasoning` 写成独立字段 `reasoning_content`，MUST NOT 拼进 `content`。`local` / `modelscope` 仍不回传思考。
- 不引入百炼 SDK、不新增 `--provider`、不在 TUI 增加 `/provider`。不做联网搜索、代码解释器、文档/PPT、音视频输入等百炼扩展字段。

## Capabilities

### New Capabilities

（无。配置与推理行为落在现有 capability。）

### Modified Capabilities

- `runtime-config`：`MAX_PROVIDER` 允许 `bailian`；新增 `MAX_BAILIAN_WORKSPACE`；`bailian` 默认模型与密钥/Workspace 校验。
- `multimodal-inference`：第三条后端、北京专属域名、云端 tools、`bailian` 思考回传、serve 拒绝与错误文案。

## Impact

- 代码：`config.py`、`cli.py`、`lifecycle.py`、`inference/client.py`、相关测试、`.env.example`。
- 依赖：不新增 SDK。
- 不改：LangGraph 节点、桌面工具协议、OCR、会话 JSON 布局、`/model` 已删除的约定。
- 实现完成后（归档时）再同步 README；本提案阶段不改代码。
