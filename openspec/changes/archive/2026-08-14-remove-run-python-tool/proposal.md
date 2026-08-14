## Why

`run_python` 是早期工作区沙箱遗留：任意执行 Python 片段，既不是 GUI Agent 的主路径，又需要单独防 `pyautogui` 绕过。产品已转向文件、OCR 与桌面操作，这段代码执行面应拿掉。

## What Changes

- **BREAKING**：默认工具注册表不再暴露 `run_python`；模型再调用该名称时按未知工具处理
- 删除 `src/max_gui/tools/python.py` 及其注册、测试与对外说明
- 工作区确认门只保留 `write_file`；「禁止经 Python 沙箱控制桌面」整条需求随工具一并作废
- 不改文件、搜索、图像、OCR、桌面工具的行为；不改 `tool_timeout` 配置项（其它工具仍可能使用）

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `agent-tools`：删除沙箱 Python 执行与禁止经沙箱控制桌面两条需求；破坏性确认仅覆盖 `write_file`

## Impact

- 代码：从 `build_default_registry` 去掉 `python_tool`；删除 `tools/python.py`；更新包说明与相关测试
- 协议：发给模型的 tools schema 不再包含 `run_python`
- 确认门：`workspace` 范围仍由 `write_file` 使用，桌面确认策略不变
- 文档：归档后同步 `AGENTS.md`、`README.md`，以及仍点名该工具的 `docs/gui-tools.md`、`docs/windows11-compatibility.md`
- 依赖：无新增；不因本次删除收缩项目依赖
