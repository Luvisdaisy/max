## 1. 依赖与配置

- [x] 1.1 将 `ruff` 加入 `pyproject.toml` 的 `dev` 依赖组并 `uv lock`
- [x] 1.2 写入 `[tool.ruff]`：`target-version = "py312"`、`line-length = 100`、排除 `artifacts`/`model`/`.venv`
- [x] 1.3 写入 lint：`select = ["E", "W", "F", "I", "UP", "B", "RUF"]`，`ignore = ["E501", "RUF001", "RUF002", "RUF003"]`

## 2. 格式化与修通

- [x] 2.1 对 `src/` 与 `tests/` 运行 `uv run ruff format`
- [x] 2.2 运行 `uv run ruff check --fix`，手工处理剩余问题，使 `ruff check` 与 `ruff format --check` 退出码为 0

## 3. 文档与测试

- [x] 3.1 在 `AGENTS.md` 增加编码规范（Ruff 命令、行宽 100、双引号、公开函数类型标注）
- [x] 3.2 在 `README.md` 补充 `uv run ruff format` 与 `uv run ruff check`
- [x] 3.3 新增 `tests/test_style.py`，断言 `ruff check src tests` 退出码为 0
- [x] 3.4 在 `openspec/config.yaml` 的 context 中记录 Ruff 为唯一格式化工具
