## 1. Ruff 质量基线

- [x] 1.1 将固定版本的 Ruff 加入根依赖清单，并在 `pyproject.toml` 配置 Python 3.12、格式化、基础 lint 规则与 `src/`、`tests/` 检查范围。
- [x] 1.2 运行 Ruff 自动格式化和可自动修复的基础 lint，修正剩余问题，使 `ruff format --check` 与 `ruff check` 均通过。
- [x] 1.3 更新或新增自动化测试，验证项目配置与依赖清单声明 Ruff 和预期质量规则。

## 2. 持续集成门禁

- [x] 2.1 新增 GitHub Actions 工作流，在 `push` 和 `pull_request` 的 Windows + Python 3.12 环境安装根依赖清单。
- [x] 2.2 在工作流按顺序执行 Ruff 格式检查、Ruff 静态检查、完整 `unittest` 测试套件和 `python -m pip check`，且不调用模型、下载、基准或桌面控制命令。
- [x] 2.3 为工作流触发条件、平台版本和质量命令添加配置级测试或等效结构校验。

## 3. 文档与验证

- [x] 3.1 更新 `README.md` 与 `tech-design.md`，说明本地质量检查、修复命令、CI 门禁以及不加载模型的边界。
- [x] 3.2 执行 Ruff 格式检查、Ruff 静态检查、完整单元测试、`python -m pip check`、OpenSpec 严格验证和 `git diff --check`，记录结果。
