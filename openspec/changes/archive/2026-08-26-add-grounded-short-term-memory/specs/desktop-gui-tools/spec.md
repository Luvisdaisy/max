## MODIFIED Requirements

### Requirement: 定位编号跨回合保留
成功的 `locate` MUST 把编号到逻辑中心的映射写入当前会话，且该映射 MUST 绑定生成它的当前截图坐标帧。后续用户回合在同一会话中按 `target_id` 移动时，只有尚未成功生成新截图且当前帧仍为该定位来源时才可命中；任何成功 `screenshot`（包括 `mouse_move` 或破坏性动作的后置截图）MUST 清空旧编号。会话 JSON 缺少该字段时 MUST 视为没有定位结果。

#### Scenario: 下一回合按未刷新帧编号移动
- **WHEN** 上一回合 `locate` 在当前截图上记下 `id=1` 的逻辑中心，且新回合开始前未成功生成新截图
- **THEN** 新回合调用 `mouse_move(target_id=1)` 指针移到该逻辑中心，且 MUST NOT 报没有该编号

#### Scenario: 新截图后旧编号不可移动
- **WHEN** 当前帧的 `locate` 已生成 `id=1`，随后成功生成新的截图
- **THEN** 后续调用 `mouse_move(target_id=1)` 返回中文错误而不移动指针

## ADDED Requirements

### Requirement: 新截图使定位事实与编号同步失效
每次成功 `screenshot` 创建或覆盖当前 `ViewFrame` 时，系统 MUST 清空绑定旧帧的可执行 `locate_hits`，并使对应短期定位事实失效。仅当前活动 `ViewFrame.image_path` 上、`coordinate_space=view` 且非观察专用的 `locate` 结果可创建有效定位事实。历史图、带框副本、空结果或定位失败 MUST NOT 留下有效定位事实。

#### Scenario: 新截图后事实摘要不再提供旧编号
- **WHEN** 当前帧的 `locate` 已生成 `id=1`，随后成功生成新的截图
- **THEN** 模型事实摘要不再提供 `id=1`

#### Scenario: 观察专用定位不写入事实
- **WHEN** 模型对历史截图或带框副本调用 `locate`
- **THEN** 结果仍可供观察，但不会创建可执行定位事实或可供移动的编号
