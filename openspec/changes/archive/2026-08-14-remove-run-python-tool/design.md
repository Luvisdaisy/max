## Context

默认注册表当前装配 `read_file` / `write_file` / `list_dir` / `search_files` / `run_python` / `prepare_image` / `ocr` / `ocr_locate` 与桌面工具。`run_python` 在 `src/max_gui/tools/python.py`：`python -c` 子进程、工作区 cwd、超时、AST 拦截桌面控制库，确认范围为 `workspace`。

产品路径已是 GUI Agent。这段任意代码执行不是主能力，却扩大攻击面，并单独占用「禁止经沙箱控制桌面」需求。调用方只有 `build_default_registry` 与 `tests/test_tools.py`。

## Goals / Non-Goals

**Goals:**

- 从默认注册表拿掉 `run_python`，模型再调用时走已有未知工具路径
- 删除实现模块与专属测试，避免留下可再挂上的死代码
- 把工作区确认门收成只覆盖 `write_file`
- 归档时同步项目说明，去掉「沙箱 Python」表述

**Non-Goals:**

- 不提供替代代码执行工具（shell、notebook、受限 eval）
- 不改 `tool_timeout` 配置或其它工具的超时用法
- 不改桌面确认、文件路径沙箱、OCR、推理客户端
- 不清理已归档 OpenSpec 历史里对 `run_python` 的记录

## Decisions

### 1. 整工具删除，而不是隐藏或改成未知别名

备选：保留模块但不注册；或注册后立即返回「已停用」。不采用。隐藏模块仍是后门入口；停用别名会让 schema 继续占模型上下文。删除文件与注册即可；未知名称已由 `ToolRegistry` 返回中文错误。

### 2. 确认门只动覆盖范围

`confirmation_scope` 协议与 `SessionScopedGate` 保留。`write_file` 仍是 `workspace`。去掉 `run_python` 后，工作区自动批准只影响写文件，桌面策略不变。

### 3. 文档与测试一起收口

- 删 `test_run_python_success_and_timeout`、`test_run_python_blocks_pyautogui`
- `test_unknown_tool_and_confirmation_deny` 去掉对 `run_python` 的拒绝分支，保留未知工具与 `write_file` 拒绝
- 归档后改 `AGENTS.md`、`README.md`、`docs/gui-tools.md`、`docs/windows11-compatibility.md` 中仍点名该工具的句子；已归档 change 不改

## Risks / Trade-offs

- [模型仍按旧习惯调用 `run_python`] → 未知工具错误回 `observe`，图继续；工具描述不再出现该名
- [用户仍想在工作区跑脚本] → 本变更明确不做替代；需要时另开 change
- [Win11 编码问题随文件删除消失，调研文档若仍写「待修」会过时] → 归档时改成「工具已移除」一句，不扩写

## Migration Plan

- 实现即生效：新会话 schema 不再含 `run_python`
- 旧会话 JSON 里若有历史 tool 消息可继续只读展示，无需迁移
- 回滚：从本 change 还原 `python.py` 与注册即可

## Open Questions

无。范围已由「移除该工具」锁定。
