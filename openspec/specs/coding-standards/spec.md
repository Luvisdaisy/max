# coding-standards Specification

## Purpose

项目编码规范：Ruff 作为唯一格式化与 lint 工具，配置与文档约定保持一致。

## Requirements

### Requirement: 使用 Ruff 作为唯一格式化与检查工具

项目 MUST 将 `ruff` 列入 `dev` 依赖，并在 `pyproject.toml` 提供 `[tool.ruff]` 配置。贡献者与助手 MUST 使用 `uv run ruff format` 格式化、`uv run ruff check` 检查 `src/` 与 `tests/`。项目 MUST NOT 再引入 Black、独立 isort 或 flake8 作为并行格式化/检查工具。

#### Scenario: 开发环境可运行 Ruff

- **WHEN** 执行 `uv sync --group dev` 后运行 `uv run ruff --version`
- **THEN** 命令成功，且能读取 `pyproject.toml` 中的 Ruff 配置

#### Scenario: 检查源码与测试

- **WHEN** 执行 `uv run ruff check src tests`
- **THEN** 退出码为 0

#### Scenario: 格式化入口存在

- **WHEN** 执行 `uv run ruff format --check src tests`
- **THEN** 退出码为 0（工作区已按配置格式化）

### Requirement: Ruff 配置与仓库风格一致

Ruff 配置 MUST 以 Python 3.12 为目标，行宽 MUST 为 100。lint MUST 至少启用 pycodestyle（E/W）、Pyflakes（F）、isort（I）、pyupgrade（UP）、bugbear（B）与 Ruff（RUF）。配置 MUST 忽略由 formatter 处理的 `E501`，以及针对中文全角标点的 `RUF001`、`RUF002`、`RUF003`。配置 MUST NOT 默认启用 ANN、pydocstyle（D）或 bandit（S）。

#### Scenario: 行宽与目标版本

- **WHEN** 读取 `pyproject.toml` 的 `[tool.ruff]`
- **THEN** `target-version` 为 `py312`，`line-length` 为 `100`

#### Scenario: 规则集不强制注解与 docstring

- **WHEN** 读取 `[tool.ruff.lint]`
- **THEN** `select` 包含 `E`、`W`、`F`、`I`、`UP`、`B`、`RUF`，且不包含 `ANN`、`D`、`S`

### Requirement: 项目文档记录编码规范

`AGENTS.md` MUST 包含编码规范：代码标识符使用英文、公开函数使用类型标注、Ruff 为唯一格式化工具、提交或完成实现前运行 format 与 check。`README.md` MUST 给出对应的 `uv run ruff` 命令。

#### Scenario: 助手能读到规范

- **WHEN** 阅读 `AGENTS.md`
- **THEN** 能找到 Ruff 命令以及行宽、引号等风格约定

#### Scenario: README 给出开发命令

- **WHEN** 阅读 `README.md`
- **THEN** 文档包含 `uv run ruff format` 与 `uv run ruff check`
