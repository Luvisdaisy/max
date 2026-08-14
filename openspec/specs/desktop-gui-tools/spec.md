# desktop-gui-tools Specification

## Purpose

基于 PyAutoGUI 的桌面感知与执行（截图、屏幕信息、移鼠、点按、拖拽、输入文本、按键），含逻辑坐标、权限错误与安全约束。

## Requirements

### Requirement: 截取主屏并返回逻辑元数据

`screenshot` MUST 截取主屏（或给定逻辑像素 `region`），把 PNG 写入 `artifacts/screenshots/`，并返回文本摘要：路径、逻辑宽高、`scale`、当前光标坐标。全黑或过小的图像 MUST 视为屏幕录制权限失败，返回中文步骤，且 MUST NOT 把空图发给模型。默认 MUST 在图上标注当前光标位置。

#### Scenario: 全屏截图成功

- **WHEN** 模型调用 `screenshot` 且屏幕录制已授权
- **THEN** 工具写入 PNG，摘要包含 `path`、`width`、`height`、`scale`、`cursor`，并附带该图像引用

#### Scenario: 未授权得到黑图

- **WHEN** 截图结果全黑或尺寸过小
- **THEN** 工具返回屏幕录制授权的中文步骤，且不把该图作为模型输入

### Requirement: 查询屏幕与指针

`screen_info` MUST 返回主屏逻辑分辨率、`scale` 与当前鼠标逻辑坐标。MUST NOT 要求确认。

#### Scenario: 读取屏幕信息

- **WHEN** 模型调用 `screen_info`
- **THEN** 结果包含 `screen_width`、`screen_height`、`scale`、`mouse_x`、`mouse_y`

### Requirement: 逻辑坐标移动指针

`mouse_move` MUST 使用逻辑像素将指针移到 `(x, y)`。越界坐标 MUST 夹紧到主屏内，并在结果中说明。MUST NOT 要求确认。

#### Scenario: 移动到可见点

- **WHEN** 模型调用 `mouse_move`，坐标在主屏内
- **THEN** 指针移动到该逻辑坐标

#### Scenario: 越界夹紧

- **WHEN** 模型调用 `mouse_move`，`x` 或 `y` 超出主屏
- **THEN** 指针移到夹紧后的位置，结果说明发生了夹紧

### Requirement: 点击与拖拽需确认

`mouse_click` MUST 支持左/右/中键与单击/双击；若提供坐标则先移动再点击。`mouse_drag` MUST 从 `(x1, y1)` 拖到 `(x2, y2)`。二者 MUST 要求确认，会话普通自动批准 MUST NOT 跳过。

#### Scenario: 带坐标单击

- **WHEN** 用户批准 `mouse_click`，参数为屏幕内的 `x`、`y`
- **THEN** 指针先移到该点再单击左键

#### Scenario: 拒绝拖拽

- **WHEN** 模型调用 `mouse_drag` 且用户拒绝
- **THEN** 不移动指针、不按下鼠标，工具结果为已取消

### Requirement: 输入文本与按键分离

`keyboard_type` MUST 只接受文本并写入当前前台窗口；MUST NOT 接受按键名。含非 ASCII 的文本 MUST 通过剪贴板粘贴，不得静默丢字。`keyboard_press` MUST 只接受白名单键名或组合键；MUST NOT 接受自由文本。白名单外的键名 MUST 拒绝。关机或退出登录相关组合 MUST 拒绝。二者 MUST 要求确认，会话普通自动批准 MUST NOT 跳过。

#### Scenario: 写入 ASCII 文本

- **WHEN** 用户批准 `keyboard_type`，`text` 为 `1+1`
- **THEN** 该文本被输入到当前前台窗口

#### Scenario: 按下回车

- **WHEN** 用户批准 `keyboard_press`，`keys` 为 `enter`
- **THEN** 系统按下回车，且不把 `enter` 当作普通文本写入

#### Scenario: 拒绝未知键名

- **WHEN** 模型调用 `keyboard_press`，`keys` 含白名单外的名称
- **THEN** 工具返回错误且不发送按键

#### Scenario: 拒绝危险热键

- **WHEN** 模型调用 `keyboard_press`，`keys` 为退出登录或关机相关组合
- **THEN** 工具返回错误且不发送按键

### Requirement: 桌面调用不阻塞界面

桌面后端的同步调用 MUST 在工作线程中执行。生产实现 MUST 开启 failsafe，并在连续动作之间加入短暂暂停。测试 MUST 注入假后端，MUST NOT 在 CI 中驱动真实鼠标、键盘或屏幕。

#### Scenario: 假后端记录点击

- **WHEN** 测试用假后端调用 `mouse_click`
- **THEN** 后端记录调用参数，真实指针位置不变

### Requirement: 权限失败对用户可读

屏幕录制或辅助功能缺失时，工具 MUST 返回可照做的中文步骤（系统设置中的屏幕录制 / 辅助功能，勾选运行本程序的终端）。MUST NOT 只抛出未翻译的英文异常。

#### Scenario: 辅助功能未授权

- **WHEN** 键鼠 API 因辅助功能权限失败
- **THEN** 工具结果包含中文授权步骤，图继续进入 `think`
