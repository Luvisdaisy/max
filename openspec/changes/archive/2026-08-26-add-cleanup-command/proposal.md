## Why

`artifacts/screenshots/`、`artifacts/runs/` 与 `artifacts/sessions/` 当前默认长期保留，开发调试过程中会持续占用磁盘，也缺少统一的手动清理入口。新增 `max-gui cleanup`，让用户可以明确且安全地一次清除这三类本地记录。

## What Changes

- 新增 `max-gui cleanup` 子命令，清除工作区下截图、运行事件和会话记录目录中的内容。
- 清理前默认要求用户交互确认；提供 `--yes` 跳过确认，便于脚本化使用。
- 清理完成后保留三个记录目录本身，并输出清理结果。
- 清理失败时报告失败路径与原因，并以非零状态退出。

## Capabilities

### New Capabilities

- `cleanup-command`: 提供清理本地截图、运行与会话记录的命令行能力及安全确认契约。

### Modified Capabilities

无。

## Impact

- 影响 `src/max_gui/cli.py` 及记录目录路径配置。
- 新增清理逻辑与 CLI 行为测试。
- 不新增依赖，不改变 TUI、Agent 运行和记录写入逻辑。
- 该命令会永久删除指定目录中的本地记录，属于破坏性操作。
