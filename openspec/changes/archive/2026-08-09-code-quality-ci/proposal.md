## Why

当前仓库缺少统一的自动格式化、静态检查和持续集成门禁，代码质量只能依赖本地人工执行。建立可复现的质量基线，能在合并前尽早发现格式、lint、依赖和单元测试回归。

## What Changes

- 在 `pyproject.toml` 定义 Ruff 的格式化与静态检查规则，覆盖 `src/` 和 `tests/`。
- 将固定版本的 Ruff 纳入项目的开发安装清单，并提供本地一致的格式检查、lint、单元测试和依赖一致性命令。
- 新增 GitHub Actions 工作流，在 Windows 与 Python 3.12 环境执行 `ruff format --check`、`ruff check`、单元测试和 `pip check`。
- 更新开发文档与技术设计，明确质量门禁、失败处理及 CI 不下载或加载本地模型的边界。

## Capabilities

### New Capabilities

无。本变更仅建立开发工具与自动化门禁，不改变产品运行时行为。

### Modified Capabilities

无。本变更不改变现有行为规格。

## Impact

- 受影响配置：`pyproject.toml`、`requirements.txt`、GitHub Actions 工作流及开发文档。
- 新增开发工具依赖 Ruff；不新增模型、网络推理或桌面控制行为。
- 贡献者与 CI 均需遵循相同的 Windows/Python 3.12 质量检查流程。
