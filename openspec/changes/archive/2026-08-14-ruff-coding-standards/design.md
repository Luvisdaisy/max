## Context

项目用 `uv` 管理 Python 3.12 环境，开发依赖只有 pytest。代码已普遍使用 `from __future__ import annotations`、双引号和类型标注，但边界处有意 `except Exception` 和少量未标注回调。缺少单一格式化/检查入口，风格只能靠目视。

## Goals / Non-Goals

**Goals:**

- 用 Ruff 同时做格式化与 lint，配置写在 `pyproject.toml`
- 规则贴近现有代码，避免为通过检查做大范围重构
- 规范写进 `AGENTS.md` / `README.md`，助手和贡献者有同一套命令
- 当前 `src/` 与 `tests/` 在 `ruff format` 与 `ruff check` 下通过

**Non-Goals:**

- 不上 pre-commit、GitHub Actions 或其他 CI
- 不引入 Black、isort 可执行文件、mypy 或 pydocstyle
- 不强制全量 docstring、不强制 flake8-annotations / bandit
- 不改运行时行为或公开 CLI 接口

## Decisions

### 1. 只用 Ruff，配置集中在 pyproject.toml

`ruff` 加入 `[dependency-groups] dev`。格式化用 `ruff format`，检查用 `ruff check`。`target-version = "py312"`，`line-length = 100`（现有行宽接近此值，79 会制造大量无意义换行）。

- 备选：Black + isort + flake8。不采用：三套工具、两份配置，与「保持简单」冲突。

### 2. 启用与现有风格匹配的规则集

`lint.select`：`E`、`W`、`F`、`I`、`UP`、`B`、`RUF`。

- `I` 替代独立 isort
- `UP` 按 3.12 升级过时写法
- `B` 抓常见缺陷
- 忽略 `E501`：行宽交给 formatter
- 忽略 `RUF001` / `RUF002` / `RUF003`：用户可见中文文案必须使用全角标点，不能改成半角

不启用：`ANN`（回调/测试夹具会大量误报）、`BLE`（TUI 与工具边界必须吞异常并回图）、`D`（项目不要求文档字符串）、`S`（本地 Agent 场景噪声高）。

已有 `# noqa: BLE001` / `ANN001` 可保留；若对应规则未启用，Ruff 可能报无用 noqa，届时删掉或改 `RUF100` 处理。

### 3. 格式化默认值与仓库习惯对齐

`quote-style = "double"`，`indent-style = "space"`，`line-ending = "lf"`。排除 `artifacts/`、`model/`、`.venv`。

### 4. 规范写在 AGENTS.md，命令写在 README

`AGENTS.md` 增加「编码规范」：标识符英文、公开函数类型标注、禁止第二套格式化工具、改完代码跑 `uv run ruff format` 与 `uv run ruff check`。`README.md` 开发命令补这两条。`openspec/config.yaml` 可加一句 context，方便后续提案带上约定。

### 5. 用测试锁住检查通过

`tests/test_style.py` 调用 `ruff check src tests`，退出码必须为 0。避免配置回退后无人发现。

## Risks / Trade-offs

- [首次 format 会改很多文件] → 本变更一次格式化并跑完全部测试；不与功能改动混在同一提交意图里
- [过严规则逼出无意义 noqa] → 规则集从窄到够用，不为「更严」加 ANN/D/S
- [无 CI 时有人忘跑 ruff] → `AGENTS.md` 写明助手必须跑；后续若要 CI 另开 change

## Migration Plan

1. 加依赖与配置
2. `ruff format` + `ruff check --fix`
3. 手工处理剩余问题
4. 更新文档并补 `test_style`
5. 回滚：移除 `ruff` 依赖与 `[tool.ruff]`，还原格式化 diff

## Open Questions

无。
