## Why

仓库已用 `uv` 和 pytest，但没有统一的格式化与静态检查。`AGENTS.md` 里的提交示例提到 ruff，实际 `pyproject.toml` 未配置，开发环境也装不上 `ruff`。风格靠手写和零散 `noqa`，容易漂移。

## What Changes

- 将 `ruff` 加入 `dev` 依赖组
- 在 `pyproject.toml` 配置 Ruff：格式化 + 与现有代码匹配的 lint 规则
- 用 Ruff 格式化并修通 `src/` 与 `tests/` 的现有违规
- 在 `AGENTS.md` 与 `README.md` 写明编码规范与常用命令
- 不引入 pre-commit、CI 工作流或 Black/isort 等第二套工具

## Capabilities

### New Capabilities

- `coding-standards`: 项目编码规范与 Ruff 格式化/检查约定

### Modified Capabilities

## Impact

- `pyproject.toml`、`uv.lock`：新增 `ruff` 开发依赖与 `[tool.ruff]` 配置
- `src/max_gui/`、`tests/`：按 Ruff 格式化，必要时做小范围 lint 修复
- `AGENTS.md`、`README.md`：补充风格约定与 `uv run ruff` 命令
- 运行时行为、TUI、Agent、工具协议不变
