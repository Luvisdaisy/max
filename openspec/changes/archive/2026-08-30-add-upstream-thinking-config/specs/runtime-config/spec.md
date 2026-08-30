## ADDED Requirements

### Requirement: 统一上游思考配置

系统 MUST 识别 `MAX_GUI_ENABLE_THINKING`，并把其解析为 `Settings.enable_thinking`。环境变量
缺失时 MUST 为 `false`；仅不区分大小写的 `true` 与 `false` 为合法值。非法非空值 MUST 在
加载配置时以中文错误拒绝，且 MUST NOT 启动 TUI。`.env.example` 与 README MUST 说明该值控制
上游模型是否生成思考，而不是隐藏已经返回的 reasoning。

#### Scenario: 缺省关闭

- **WHEN** 未设置 `MAX_GUI_ENABLE_THINKING`
- **THEN** `Settings.enable_thinking` 为 `false`

#### Scenario: 显式开启

- **WHEN** `MAX_GUI_ENABLE_THINKING=TrUe`
- **THEN** `Settings.enable_thinking` 为 `true`

#### Scenario: 非法值被拒绝

- **WHEN** `MAX_GUI_ENABLE_THINKING=auto`
- **THEN** 加载配置失败，错误信息为中文且包含该变量名
