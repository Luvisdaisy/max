## Context

项目当前使用 `unittest`，但尚未定义统一的格式化或 lint 配置，也没有 CI 工作流。运行时依赖由根目录 `requirements.txt` 安装，项目约束要求支持 Windows 与 Python 3.12，且 CI 不得依赖或加载 `model/` 中的大模型。

## Goals / Non-Goals

**Goals:**

- 用 Ruff 建立可重复的格式与静态检查基线。
- 让本地开发与 GitHub Actions 执行同一套质量门禁。
- 在 CI 中验证依赖一致性和全部单元测试，而不访问模型或桌面环境。

**Non-Goals:**

- 不迁移测试框架、不引入覆盖率阈值或类型检查器。
- 不运行 Textual 交互界面、真实 GPU 推理、模型下载、基准或桌面控制。
- 不自动格式化开发者工作区；门禁仅检查格式状态。

## Decisions

### 使用 Ruff 作为单一格式与 lint 工具

在 `pyproject.toml` 集中定义 Python 3.12 目标版本、检查范围、排除路径和有限的基础规则集。Ruff 以固定版本列入根安装清单，使本地与 CI 解析相同工具版本。

备选方案是 Black 加 Flake8 或仅执行格式化。前者增加多个配置和版本面，后者无法发现常见的导入、未使用变量等静态问题，因此不采用。

### GitHub Actions 使用 Windows + Python 3.12 的单一质量作业

新工作流在 `push` 与 `pull_request` 触发，在 Windows runner 创建 Python 3.12 环境，使用 `python -m pip install -r requirements.txt` 安装后依次运行 `ruff format --check`、`ruff check`、`python -m unittest discover -s tests -v` 与 `python -m pip check`。

选择 Windows 与项目支持平台一致；选择单一作业而非矩阵，避免下载包含 GPU 与桌面依赖的多套环境。CI 不传递模型路径，也不调用 `max-agent`、基准或下载命令。

### 文档给出检查和修复的明确分工

README 与技术设计将列出检查命令和开发者主动修复命令（`ruff format`、`ruff check --fix`）。CI 仅使用检查模式，确保不会在远程运行中改写代码。

## Risks / Trade-offs

- [现有代码首次不符合 Ruff] → 实施时先运行检查，按配置修正受影响文件，并以检查通过作为任务完成条件。
- [Windows CI 安装大型运行时依赖耗时] → 保持单一 Python 版本和单一作业；后续如有稳定需求再单独规划依赖缓存或矩阵。
- [Ruff 规则过严导致无关重构] → 初始仅启用格式与基础 lint，新增规则须经独立变更评审。

## Migration Plan

1. 添加配置、固定 Ruff 依赖和工作流文件。
2. 格式化并修复现有代码，使本地完整门禁通过。
3. 在分支与拉取请求中观察 CI 结果；如需回退，可移除工作流和 Ruff 配置，不影响运行时命令或模型文件。
