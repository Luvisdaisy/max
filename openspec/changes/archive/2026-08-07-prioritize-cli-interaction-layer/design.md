## Context

当前项目的命令入口已经使用 Typer，终端输出使用 Rich，交互控制台同时存在 Prompt Toolkit 和 Textual 实现。现有代码中 Prompt Toolkit 已具备可测试的行式循环，Textual 仍是独立的 UI 壳。目标是先验证命令分发、状态反馈和后续 Agent 工具边界，再决定是否投入更复杂的终端 UI。

## Goals / Non-Goals

**Goals:**

- 让 Typer 成为公开命令语法的唯一入口。
- 让 Rich 负责主要终端输出、状态和错误展示。
- 让 Prompt Toolkit 承担默认的交互式会话，覆盖输入、历史、`/doctor`、`/quit` 和未配置后端提示。
- 保留 UI 无关的共享分发核心，确保未来 Textual 只是可替换的展示适配器。
- 把 Textual 调整为显式选择的后续高级 UI，不能影响 CLI 基础交互可用性。

**Non-Goals:**

- 本次不实现 AI 聊天后端、模型自动加载、桌面控制或 Agent 闭环。
- 本次不删除 Textual 依赖或代码，不改变其作为后续高级 UI 的扩展位置。
- 不改变 Doctor、模型下载、模型校验、离线基准和 Artifact Store 的业务语义。

## Decisions

### Typer owns command routing

Typer 继续负责公开命令、选项、退出码和默认入口判断。这样可以让脚本调用和交互式调用共享同一套参数语义，避免在多个 UI 框架中重复定义命令。

备选方案是让 Textual 作为应用根入口，再由 UI 回调解析命令；该方案会把非交互 CLI 语义绑定到 UI 生命周期中，降低自动化测试和无终端运行的可靠性，因此不采用。

### Prompt Toolkit is the primary interactive adapter

默认无子命令入口和 `--chat` 进入 Prompt Toolkit 行式控制台，Rich 负责消息和结果渲染。共享 `console_core` 只返回结构化操作结果，Prompt Toolkit 不直接实现 Doctor、模型或桌面业务逻辑。

备选方案是保留 Textual 默认、Prompt Toolkit fallback。该方案需要优先处理 Textual 初始化、布局和终端兼容性，不符合先完成 CLI 基础交互层的目标，因此改为 Textual 后置。

### Textual is an optional advanced frontend

Textual 保留为后续高级 UI，可在显式选择且依赖可用时启动。它必须调用与 Prompt Toolkit 相同的分发核心，不能产生另一套命令、状态或安全语义。Textual 不能成为基础 CLI 运行的硬依赖。

### Keep the dispatch contract stable

继续使用 `OperationResult` 和 `dispatch_input` 作为前端适配边界。未来增加 Textual、高级状态面板或其他 UI 时，只新增渲染适配器，不把业务逻辑搬入 UI 回调。

## Risks / Trade-offs

- [Prompt Toolkit 的交互布局弱于 Textual] → 先保证命令、历史和状态反馈正确，将复杂布局留到后续 Textual 阶段。
- [默认入口行为改变导致旧脚本预期不一致] → 保留 `--chat`、Doctor 和现有开发命令，并增加默认入口与显式入口测试。
- [Textual 代码长期未被调用而产生漂移] → 保留共享分发契约测试，并在后续启用 Textual 时补充显式 smoke test。
- [终端不可用时交互启动失败] → 继续支持非交互 Doctor 和模型操作；基础交互路径只依赖可用的 CLI/Prompt Toolkit 环境。

## Migration Plan

1. 更新 CLI 默认入口和 `--chat` 路由，使其选择 Prompt Toolkit。
2. 调整 `--fallback` 的语义或兼容处理，避免把默认实现误称为 fallback。
3. 更新前端和命令分发测试，覆盖默认入口、`--chat`、`/doctor`、`/quit`、未配置后端和 Textual 不可用场景。
4. 同步 README、`tech-design.md`、架构报告和周报的技术栈与交互入口说明。
5. 回滚时恢复 Textual 默认路由即可，不涉及数据迁移或模型产物迁移。
