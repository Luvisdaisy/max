## ADDED Requirements

### Requirement: 持久化任务级已落地事实
会话 JSON 的 `task_context` MUST 允许持久化 `grounded_facts`，以便同一未完成任务的中断恢复继续使用当前仍有效的事实。旧会话缺少该字段、字段不是列表或条目缺少必要字段时 MUST 正常加载，并把无效条目丢弃。会话切换或开始新的用户任务 MUST NOT 把上一任务的事实带入新任务。

#### Scenario: 中断后保留当前帧事实
- **WHEN** 用户在拥有有效定位事实的任务中中断并恢复同一 checkpoint，且活动视图帧仍与事实来源一致
- **THEN** 恢复后的任务上下文保留该事实并可向模型提供其摘要

#### Scenario: 新任务不继承旧事实
- **WHEN** 同一会话开始新的用户任务
- **THEN** 新任务的 `grounded_facts` 为空，旧任务事实不会进入其模型上下文
