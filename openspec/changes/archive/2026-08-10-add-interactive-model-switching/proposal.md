## Why

当前聊天运行时固定使用 Qwen3.5-2B，开发者无法查看项目已下载的其他本地模型，也不能在不重启会话的情况下切换模型。需要提供受限于项目 `model/` 目录的模型发现和会话内选择能力，以便复用本地模型并保持离线边界。

## What Changes

- 新增 `/model` 交互命令：无参数时列出 `model/` 下所有模型目录的相对名称与当前选择；带模型名称时选择该模型。
- 支持用户在 Textual 会话中随时切换到已发现的模型；切换后清空当前会话历史，并在下一条普通消息时按新选择懒加载模型。
- 将本地聊天运行时从固定的 Qwen3.5-2B 路径改为以已选择的本地模型目录为输入，同时保持只使用本地文件、无网络回退的边界。
- 对不存在、非目录或不完整的模型提供明确的会话内错误，保留原模型选择和可继续交互的会话。

## Capabilities

### New Capabilities
- `interactive-model-selection`: 发现项目 `model/` 目录下的模型并在单个交互会话内选择和切换模型。

### Modified Capabilities
- `chat-console-ui`: 增加 `/model` 斜杠命令的输入、选择反馈和帮助展示。
- `local-llm-runtime`: 将固定模型加载契约调整为按会话选择的本地模型目录进行验证、懒加载与切换。

## Impact

- 受影响代码：`src/max_agent/cli.py`、`console_core.py`、`console_frontends.py`、`local_llm.py` 及对应测试。
- 不新增远程模型服务或自动下载行为；模型仅从仓库根目录的 `model/` 读取。
- `tech-design.md` 需要同步当前实现基线与交互工作流。
