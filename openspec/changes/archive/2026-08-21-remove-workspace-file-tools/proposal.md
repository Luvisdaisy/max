## Why

工作区 `read_file` / `write_file` / `list_dir` / `search_files` 是第一周 coding agent 残留。当前产品是桌面 GUI Agent：系统契约要求桌面任务一律键鼠完成。这四个工具挤占 schema，并给模型一条不碰屏幕的捷径，和主路径打架。

## What Changes

- **BREAKING**：默认工具注册表不再暴露 `read_file`、`write_file`、`list_dir`、`search_files`。模型再调用这些名称时按未知工具处理。
- 删除 `src/max_gui/tools/files.py` 与 `src/max_gui/tools/search.py`，以及对应注册与测试。
- 保留 `paths.py`：`prepare_image` 与 OCR 仍需工作区 / 截图目录路径钉死。
- 不改桌面工具、OCR、`prepare_image`、确认门协议本身。需要改文件时走键鼠操作 Finder / 编辑器。
- 旧会话里的历史 tool 消息只读保留，不迁移、不回放执行。

## Capabilities

### New Capabilities

（无。）

### Modified Capabilities

- `agent-tools`：删除限定工作区的文件系统工具与本地文件搜索；统一协议 / 确认门 / 文本结果场景不再以文件工具为例。
- `react-agent`：工具结果回注场景改用仍注册的工具，不再依赖 `read_file`。
- `tui-repl`：不弹确认的工具名单去掉 `write_file`。

## Impact

- 代码：`tools/files.py`、`tools/search.py`、`tools/registry.py`、`tools/__init__.py`、`tests/test_tools.py`、`tests/test_agent.py`。
- 协议：发给模型的 tools schema 不再包含上述四个名称。
- 确认门：`write_file` 不再是工作区范围内的示例工具；`SessionScopedGate` 与 `confirmation_scope` 协议保留。
- 文档：归档后同步 `README.md`（实现阶段不改对外说明）。
- 依赖：无删除、无新增。
- 不改：`paths.py`、图像预处理、OCR、桌面工具、`--workspace` 配置（OCR / 图像仍用工作区根）。
