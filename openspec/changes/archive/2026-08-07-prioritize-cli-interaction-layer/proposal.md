## Why

当前项目已经同时具备 Typer、Rich、Prompt Toolkit 和 Textual 的基础实现，但将 Textual 作为首要交互入口会增加终端 UI 的实现和调试成本，也不利于先验证 CLI 命令、状态反馈和 Agent 工具调用边界。应先以成熟、可脚本化的 CLI 交互层完成基础能力，再将 Textual 定位为后续可选的高级 UI。

## What Changes

- 将 Typer 作为公开命令入口，Rich 作为主要终端输出和状态渲染组件。
- 将 Prompt Toolkit 作为首要的交互式会话实现，优先完成命令历史、输入、退出、状态反馈和 `/doctor` 等基础交互。
- 将 Textual 从默认交互前端调整为后续可选的高级 UI，不再作为 `max-agent` 默认交互界面的首要实现。
- 修改架构报告、README、`tech-design.md` 及其他相关文档中的技术栈和交互入口表述。
- 保留共享的命令分发核心，使未来 Textual 可以复用 CLI 已验证的操作契约。
- 修订聊天控制台能力规格，明确 CLI/Prompt Toolkit 的优先级和 Textual 的后置定位。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `chat-console-ui`: 调整默认交互入口和前端优先级，要求基础 CLI/Prompt Toolkit 交互优先可用，Textual 作为后续可选高级 UI。

## Impact

- 影响 `src/max_agent/cli.py`、`src/max_agent/console_frontends.py` 和相关交互测试。
- 影响 `README.md`、`tech-design.md`、`docs/week1/architecture-report.md`、`docs/week1/weekly-report.md` 等公开文档。
- 需要重新定义 `max-agent` 无子命令、`--chat` 和 `--fallback` 的交互入口语义，并补充 CLI/Prompt Toolkit 优先路径的测试。
- 不改变模型下载、模型校验、离线基准、Doctor 证据归档和桌面控制安全边界。
