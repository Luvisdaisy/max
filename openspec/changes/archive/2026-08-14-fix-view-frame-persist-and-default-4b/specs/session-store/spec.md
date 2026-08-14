## ADDED Requirements

### Requirement: 持久化桌面视图坐标系

会话 JSON MUST 持久化最近一次成功 `screenshot` 的视图坐标系（原点、逻辑宽高、视图宽高、截图路径）。缺字段的旧会话 MUST 仍能加载，并视为尚无截图。加载会话后，后续桌面鼠标工具 MUST 使用该坐标系，直到下一次成功截图覆盖。

#### Scenario: 截图后写入会话

- **WHEN** 一次成功 `screenshot` 结束并保存会话
- **THEN** 该会话 JSON 含有视图坐标系字段，再次打开同一会话后鼠标工具按视图像素换算

#### Scenario: 旧会话缺字段

- **WHEN** 已存会话 JSON 没有视图坐标系字段
- **THEN** store 成功加载，鼠标工具视为尚无截图

### Requirement: 持久化文字定位命中表

会话 JSON MUST 持久化最近一次成功 `ocr_locate` 的编号到逻辑中心映射。缺字段的旧会话 MUST 视为空表。下一次成功定位 MUST 覆盖旧表。

#### Scenario: 定位结果可恢复

- **WHEN** 会话保存时已有 `id=1` 的定位中心
- **THEN** 重新加载后 `mouse_click` 的 `target_id=1` 仍指向同一逻辑中心
