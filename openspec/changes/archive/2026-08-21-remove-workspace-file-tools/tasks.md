## 1. 注销与删除实现

- [x] 1.1 从 `build_default_registry` 去掉 `file_tools` 与 `search_tool`，并更新 `tools/__init__.py` 与注册表 docstring
- [x] 1.2 删除 `src/max_gui/tools/files.py` 与 `src/max_gui/tools/search.py`；保留 `paths.py`

## 2. 测试与规范

- [x] 2.1 删除文件读写与搜索专属用例；未知工具 / 跳过确认门用例不再调用 `write_file`
- [x] 2.2 断言默认注册表不含 `read_file`、`write_file`、`list_dir`、`search_files`；调用这些名称返回未知工具错误
- [x] 2.3 将 `test_agent.py` 中脚本化的 `read_file` / `list_dir` 换成仍注册的工具
- [x] 2.4 运行 `uv run ruff format src tests` 与 `uv run ruff check src tests`
