# webarena-collaboration-workflows Specification

## Purpose
TBD - created by archiving change expand-webarena-product-complexity. Update Purpose after archive.
## Requirements
### Requirement: 关联协作实体与可重置业务情境

系统 SHALL 在每个 WebArena 任务中以可深拷贝的后端基线重置项目、任务、成员、活动、标签、截止日期、
子任务与评论草稿的关联状态。业务 API MUST 只返回当前可见页面需要的实体投影，评分状态 MUST 不经业务
页面或业务 API 暴露。

#### Scenario: 重置跨页编辑任务

- **WHEN** 某任务修改项目任务、子任务与评论草稿后再次被重置
- **THEN** 所有实体关系、活动记录和可见 UI 状态恢复到该任务的初始基线，评分接口不受前一次运行影响

### Requirement: 基于可见事实的跨页工作流

系统 SHALL 支持项目详情、成员工作负载、任务列表和报表之间的跨页工作流。任务成功断言 MUST 同时验证
可见导航检查点、被读取的业务事实与由该事实决定的最终实体变更。

#### Scenario: 根据项目风险调整任务负责人

- **WHEN** Agent 从项目详情读取风险项目和成员负载后，在任务页重新分配对应任务
- **THEN** 后端记录被读取事实、有效导航来源和正确的任务负责人，独立评分可验证三者关系

### Requirement: 可恢复的确定性业务反馈

系统 SHALL 为校验错误、空结果、保存成功、撤销窗口和版本冲突提供稳定且可见的反馈。冲突恢复或撤销操作
MUST 更新业务实体和活动记录，且不依赖外网、随机性或不可控延迟。

#### Scenario: 处理版本冲突后保存

- **WHEN** Agent 编辑带有过期版本的任务并看到冲突反馈后刷新并重新提交
- **THEN** 页面呈现冲突和成功反馈，后端记录最终版本、更新字段与活动事件

