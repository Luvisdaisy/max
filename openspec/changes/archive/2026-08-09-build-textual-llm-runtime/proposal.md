## Why

当前控制台仍以 Typer、Rich 和 Prompt Toolkit 为主，Textual 仅是可选界面，且普通消息没有本地模型运行时。项目已具备项目内 Qwen3.5 模型与离线基准基础，现需将其收敛为单一 Textual 聊天体验和可验证的本地 LLM 运行框架。

## What Changes

- **BREAKING** 将交互入口收敛为 `max-agent` 与 `max-agent --chat`：二者启动同一个 Textual 应用；移除 Typer 子命令、`--doctor`、`--fallback`、`--textual` 和 Prompt Toolkit 的公开启动路径。既有本地模型下载与基准实现保留为未来内部 API 或后续入口能力，本阶段不提供 CLI 调用。
- 将 Textual 设为必需交互依赖，提供聊天记录、输入状态、加载/推理状态、错误提示、`/doctor` 与 `/quit`。
- 新增本地 LLM 运行时：本阶段使用项目内已下载的 Qwen3.5-2B，以离线、懒加载方式处理纯文本聊天；Qwen3.5-4B 留作后续容量验证。模型缺失、GPU 不可用或显存不足时清楚报错且不回退网络。
- 保持 Doctor 作为 Textual 内的 slash command；不在此变更中开放桌面控制、工具调用、远程模型或模型下载。
- 更新测试、安装说明和技术设计报告，明确该版本的入口收敛与模型运行边界。

## Capabilities

### New Capabilities

- `local-llm-runtime`: 项目内 Qwen3.5-2B 的离线懒加载、纯文本生成与可诊断失败边界。

### Modified Capabilities

- `chat-console-ui`: 将默认和显式聊天入口替换为唯一的 Textual UI，并让普通聊天文本交由本地 LLM 运行时处理。
- `runtime-bootstrap`: 将 Doctor 的公开命令入口收敛为 Textual 内 `/doctor`，保留无桌面输入与机器可读证据的运行边界。

## Impact

- 代码：CLI 入口、Textual 前端、控制台分发、模型运行时与 Provider 契约；将删除不再使用的 Typer/Prompt Toolkit 交互层，但保留模型下载与基准模块作为非公开实现。
- 依赖：`textual` 保留为必需项；`typer`、`rich`、`prompt_toolkit` 将从运行依赖与统一清单中移除，前提是仓库内已无直接使用。
- 用户工作流：启动方式仅为 `max-agent` 或 `max-agent --chat`；Doctor 改在运行中的 Textual 会话使用 `/doctor`。
- 运行环境：聊天会读取 Git 忽略的 `model/Qwen/Qwen3.5-2B`；Qwen3.5-4B 不属于本阶段测试前提。不得记录模型权重、模型绝对路径或聊天文本到 Git。
