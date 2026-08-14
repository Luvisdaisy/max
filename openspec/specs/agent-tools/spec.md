# agent-tools Specification

## Purpose

统一 Function Calling 工具（文件、搜索、代码执行、图像、桌面）及结果回注。

## Requirements

### Requirement: 统一工具协议

每个工具 MUST 暴露名称、JSON schema 与异步 invoke。`act` 节点 MUST 仅按名称分发已注册工具。未知工具名 MUST 返回工具错误消息，且 MUST NOT 把异常抛出图外。

#### Scenario: 已注册工具

- **WHEN** 模型以合法路径调用 `read_file`
- **THEN** `act` 调用 `read_file`，`observe` 记录其结果

#### Scenario: 未知工具名

- **WHEN** 模型调用 `not_a_tool`
- **THEN** `observe` 收到错误字符串，图继续进入 `think`

### Requirement: 限定工作区的文件系统工具

`read_file`、`write_file`、`list_dir` MUST 将路径解析到已配置的工作区根之内。逃出工作区的路径 MUST 被拒绝。

#### Scenario: 读取工作区内文件

- **WHEN** 模型调用 `read_file`，参数为 `notes.md`，且该文件在工作区中存在
- **THEN** 工具返回文件内容

#### Scenario: 拒绝路径逃逸

- **WHEN** 模型调用 `read_file`，参数为 `../outside.txt`
- **THEN** 工具返回权限错误，且不读取该文件

### Requirement: 本地文件搜索

`search_files` MUST 在工作区下搜索文件内容，返回匹配路径与行摘录。MUST NOT 搜索工作区之外。

#### Scenario: 工作区内命中

- **WHEN** 模型调用 `search_files`，查询词出现在工作区某文件中
- **THEN** 结果包含该路径及匹配摘录

### Requirement: 沙箱 Python 执行

`run_python` MUST 在子进程中运行，带超时，工作目录为工作区，且不额外开启出站网络（v1 文档化为不允许显式外连）。超时或非零退出时，工具 MUST 返回 stdout、stderr 与退出原因。

#### Scenario: 成功片段

- **WHEN** 模型调用 `run_python`，代码为 `print(1+1)`
- **THEN** 工具结果包含 `2` 以及零退出码

#### Scenario: 超时

- **WHEN** 片段超过配置超时
- **THEN** 子进程被杀死，工具结果报告超时

### Requirement: 破坏性工具需确认

`write_file` 与 `run_python` MUST 等待用户在 TUI 中明确批准，除非该会话已开启自动批准。被拒绝的调用 MUST 返回已取消结果，且 MUST NOT 执行。会话自动批准 MUST NOT 批准桌面破坏性工具。

#### Scenario: 用户批准写入

- **WHEN** 模型调用 `write_file` 且用户确认
- **THEN** 文件被写入工作区内部

#### Scenario: 用户拒绝代码执行

- **WHEN** 模型调用 `run_python` 且用户拒绝
- **THEN** 片段不执行，工具结果为已取消

#### Scenario: 工作区自动批准不覆盖桌面

- **WHEN** 会话已开启自动批准，模型调用 `write_file` 与 `mouse_click`
- **THEN** `write_file` 无需再确认，`mouse_click` 仍需确认

### Requirement: 默认注册桌面工具

默认工具注册表 MUST 包含 `screenshot`、`screen_info`、`mouse_move`、`mouse_click`、`mouse_drag`、`keyboard_type`、`keyboard_press`。`act` MUST 仍按名称分发，未知名称行为不变。

#### Scenario: 模型调用截图

- **WHEN** 模型调用已注册的 `screenshot`
- **THEN** `act` 分发该工具，`observe` 记录其结果

### Requirement: 工具结果可携带图像引用

工具 `invoke` MUST 允许返回纯文本，或返回带文本摘要与本地图像路径的结构化结果。`act` MUST 把图像路径写入对应 tool 消息，供后续 `think` 编码。

#### Scenario: 截图结果带图

- **WHEN** `screenshot` 成功并返回图像路径
- **THEN** 追加的 tool 消息同时包含文本摘要与该路径的图像引用

#### Scenario: 文本工具保持字符串

- **WHEN** `read_file` 返回文件内容
- **THEN** tool 消息内容仍是文本，不含图像引用

### Requirement: 禁止经 Python 沙箱控制桌面

`run_python` MUST 在执行前拒绝导入 `pyautogui`、`pyscreeze`、`pynput`（含 `from ... import`）。命中时 MUST 返回中文错误，且 MUST NOT 启动子进程。

#### Scenario: 拒绝导入 pyautogui

- **WHEN** 模型调用 `run_python`，代码包含 `import pyautogui`
- **THEN** 工具返回禁止绕过桌面 API 的错误，子进程不启动

### Requirement: 桌面破坏性工具使用独立确认

`mouse_click`、`mouse_drag`、`keyboard_type`、`keyboard_press` MUST 等待用户明确批准，除非该会话开启了桌面自动批准。会话普通 `auto_approve` MUST NOT 跳过这些工具。被拒绝的调用 MUST 返回已取消结果，且 MUST NOT 执行。

#### Scenario: 普通自动批准不放行点击

- **WHEN** 会话 `auto_approve` 为真、`auto_approve_desktop` 为假，模型调用 `mouse_click`
- **THEN** TUI 仍弹出确认，在用户批准前不点击

#### Scenario: 桌面自动批准放行按键

- **WHEN** 会话 `auto_approve_desktop` 为真，模型调用 `keyboard_press`
- **THEN** 不弹确认并执行按键
