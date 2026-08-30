## ADDED Requirements

### Requirement: Policy 每轮只选择一个下一步
每次 `think` 的固定 Policy 契约 MUST 要求模型依据当前状态选择恰好一个下一步动作或在已有验证证据时完成任务。模型 MUST 通过原生 tool calling 发起动作，MUST NOT 在正文伪造 JSON 或工具调用，也 MUST NOT 输出长推理链。固定契约 MUST 要求语义元素优先、模态优先、仅使用当前快照元素、失败后不原样重复及严格完成条件。

#### Scenario: 单个副作用调用
- **WHEN** 模型需要推进当前桌面子任务
- **THEN** 该模型响应最多提交一个副作用工具调用，随后进入后置观察

#### Scenario: 有验证证据才完成
- **WHEN** 用户请求结果尚未被当前观察证实
- **THEN** 模型不得仅因工具调用返回成功而选择完成

### Requirement: 动态上下文按稳定决策段渲染
每次 `think` MUST 向模型提供紧凑、脱敏的动态上下文，顺序包含 TASK、CURRENT SUBGOAL、PROGRESS、ENVIRONMENT、VISIBLE UI、WORKING MEMORY、RECENT ACTIONS、LAST RESULT。PROGRESS MUST 区分已验证、当前、待办和不确定状态；VISIBLE UI MUST 只包含当前帧、有限且按活动模态、焦点、当前子目标相关性和近期变化排序的元素。动态上下文 MUST NOT 包含坐标、locator、完整 OCR、键盘输入正文或历史帧可执行编号。

#### Scenario: 原生文件选择器优先渲染
- **WHEN** 当前活动模态是原生文件选择器
- **THEN** VISIBLE UI 先列出该模态内的元素，且 ENVIRONMENT 标记 native UI context

#### Scenario: 近期失败进入上次结果
- **WHEN** 前一动作失败或未产生预期变化
- **THEN** LAST RESULT 包含脱敏失败原因，供下一轮选择不同策略

### Requirement: 意图与预期只用于观察验证
副作用工具 schema MUST 接受可选的短 `intent` 与受限 `expectation`。`intent` MUST 用于日志、状态摘要和重复检测，且不得要求或保存思维链；`expectation` MUST 仅来自项目规定的有限枚举。工具实现执行前 MUST 剥离这两个 Policy 元数据；`observe` MUST 在新快照中验证 expectation，只有验证通过才推进关联 progress。`task_complete` MUST 继续使用独立完成证据，不能由 intent、ToolResult 或一般 expectation 替代。

#### Scenario: 预期通过后推进进度
- **WHEN** 副作用后新快照满足 `element_selected` expectation
- **THEN** 对应 progress 项标记为已验证，并在后续上下文中显示

#### Scenario: 未变化不重复相同调用
- **WHEN** 相同工具和目标的前一调用失败或 expectation 未满足
- **THEN** 下一轮上下文提示重新观察并改变目标或策略，系统不得把该调用当作已完成
