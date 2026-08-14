## 1. 注销与删除实现

- [x] 1.1 从 `build_default_registry` 去掉 `python_tool`，并更新 `tools/__init__.py` 与注册表 docstring
- [x] 1.2 删除 `src/max_gui/tools/python.py`

## 2. 测试与规范

- [x] 2.1 删除 `run_python` 成功/超时/拦截桌面库用例；确认拒绝用例只覆盖 `write_file` 与未知工具
- [x] 2.2 断言默认注册表不含 `run_python`；调用该名返回未知工具错误
- [x] 2.3 运行 `uv run ruff format src tests` 与 `uv run ruff check src tests`
