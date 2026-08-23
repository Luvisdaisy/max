## Context

默认注册表当前装配 `read_file` / `write_file` / `list_dir` / `search_files` / `prepare_image` / `ocr` / `ocr_locate` 与桌面工具。文件与搜索在 `src/max_gui/tools/files.py`、`search.py`，路径钉死在 `paths.py`。系统契约已要求桌面任务一律键鼠，但 schema 仍暴露这四个工具。

`run_python` 已按同样理由删除。本次把文件副路径一并收掉。`prepare_image` 与 OCR 仍用 `resolve_workspace_path` / `resolve_ocr_path`，与 Finder 里改文件不是同一条能力。

## Goals / Non-Goals

**Goals:**

- 从默认注册表拿掉 `read_file`、`write_file`、`list_dir`、`search_files`
- 删除实现模块与专属测试，避免留下可再挂上的死代码
- Agent / 工具层用例改用仍注册的工具（`screenshot`、`screen_info` 等）
- 归档时从 README 去掉「工作区文件工具」表述

**Non-Goals:**

- 不提供替代的工作区读写或搜索（shell、Finder 封装、Web 搜索）
- 不删除 `paths.py`、`--workspace`、`prepare_image`
- 不改桌面工具、OCR、确认门协议（`confirmation_scope` / `SessionScopedGate` 保留）
- 不清理已归档 OpenSpec 历史里对文件工具的记录

## Decisions

### 1. 整工具删除，而不是隐藏或返回「已停用」

备选：保留模块但不注册；或注册后立即返回「已移除」。不采用。隐藏模块仍是后门；停用别名会继续占模型上下文。删除文件与注册即可；未知名称已由 `ToolRegistry` 返回中文错误。

### 2. 保留 `paths.py`

`resolve_workspace_path` 仍给 `prepare_image`；`resolve_ocr_path` 仍给 `ocr` / `ocr_locate`。文件工具删除后路径沙箱不是死代码。不把解析函数内联进图像/OCR 模块，避免无关重构。

### 3. 测试把文件工具换成桌面工具当「任意已注册工具」

- 删除 `test_read_file_and_reject_escape`、`test_search_files`
- 未知工具 / 跳过确认门用例不再调用 `write_file`，改断言 schema 不含四个名称，并用 `screenshot` 或 `keyboard_press` 覆盖「DenyGate 也挡不住」
- `test_agent.py` 里 `read_file` / `list_dir` 的脚本化调用改成 `screen_info` 或 `screenshot`，只验证 ReAct 回注与迭代上限，不验证文件内容

## Risks / Trade-offs

- [模型仍按旧习惯调用 `read_file` 等] → 未知工具错误回 `observe`，图继续；schema 不再出现这些名称
- [用户仍想在 REPL 里直接改仓库文件] → 本变更明确不做替代；需要时走桌面键鼠，或另开 change
- [工作区自动批准失去最后一个 workspace 范围工具] → 协议保留，行为真空可接受；不在本次清理确认门

## Migration Plan

- 实现即生效：新会话 schema 不再含四个文件工具
- 旧会话 JSON 里的历史 tool 消息可继续只读展示，无需迁移、不回放
- 回滚：从本 change 还原 `files.py` / `search.py` 与注册即可

## Open Questions

无。范围已由「移除 files 与 search」锁定。
