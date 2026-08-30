## ADDED Requirements

### Requirement: 新回合区分理解观察与执行观察

Agent MUST 在新用户回合构造任务上下文时把会话级历史观察标为只读背景。若用户请求桌面副作用，Agent MUST 要求当前回合先取得新的可执行截图；若用户仅询问历史画面内容，Agent MAY 基于该历史观察直接回答。

#### Scenario: 追问截图内容
- **WHEN** 新回合只询问上一张截图显示的内容
- **THEN** Agent 不执行桌面动作，并基于只读历史观察回答

#### Scenario: 新回合请求移动鼠标
- **WHEN** 新回合要求将鼠标移动到历史截图中的应用图标
- **THEN** Agent 先取得当前截图，再进行定位和移动
