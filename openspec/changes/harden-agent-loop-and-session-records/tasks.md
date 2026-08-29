## 1. 状态与恢复护栏

- [ ] 1.1 为 `TaskContext` 增加可序列化的恢复信号、失败指纹与待执行恢复策略，并兼容旧 checkpoint。
- [ ] 1.2 在 `observe` 根据工具 `exec.code`、规范化参数和当前帧更新失败计数；新截图或子任务推进时清除过期信号。
- [ ] 1.3 在工具允许集合和系统契约中落实坐标越界、重复 locate 未命中及空查询的阻断与替代观察策略。
- [ ] 1.4 达到恢复上限时生成 `recovery_exhausted` 终态，停止后续模型/工具调用并写入结构化诊断。
- [ ] 1.5 增加坐标重复、两次空定位、重复空查询、新帧解除限制和恢复耗尽的 Agent 行为测试。

## 2. 独立完成证据核验

- [ ] 2.1 为任务上下文定义待验证完成声明及其声明前观察引用的持久化表示。
- [ ] 2.2 调整 `task_complete` 分发逻辑，使其仅登记声明而不直接设置完成状态。
- [ ] 2.3 实现声明后的截图获取和确定性校验器，验证时间顺序、文件可用性及可用结构化事实。
- [ ] 2.4 将核验失败回注 `thinking`，仅在校验通过后经 `observe` 迁移至 `done`。
- [ ] 2.5 覆盖无后置截图、截图缺失、模型断言不足和校验通过的状态机测试。

## 3. 会话与运行记录去重

- [ ] 3.1 为 `Session` 增加 `run_summary`，并实现兼容的读写与类型校验。
- [ ] 3.2 将 checkpoint 改为 `message_cursor` 加恢复状态；恢复时从顶层消息重建图状态，保留旧 `checkpoint.messages` 读取兼容。
- [ ] 3.3 将大型 locate 候选明细改为按帧观察引用，工具消息、checkpoint 和任务上下文只保留必要摘要。
- [ ] 3.4 扩展运行记录器终态汇总，提供 `terminal_reason`、最后模型 `finish_reason` 与已有计数/耗时/token 数据，并投影到会话摘要。
- [ ] 3.5 为新格式恢复、旧格式兼容、无重复消息、摘要终态区分和观察引用精简添加 SessionStore/可观测性测试。

## 4. 文档与验证

- [ ] 4.1 更新 README 中会话、运行日志、截图保留和恢复诊断说明。
- [ ] 4.2 为新增或修改的 Python 模块与公开 API 补齐中文 docstring，并同步现有说明。
- [ ] 4.3 运行 `uv run ruff format src tests`、`uv run ruff check src tests`、相关 pytest，以及 `openspec validate harden-agent-loop-and-session-records --strict`。
