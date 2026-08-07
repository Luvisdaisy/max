## Why

当前项目依赖分散在 `pyproject.toml`、`requirements/base.txt`、`requirements/torch-cu130.txt` 和已准备的 Conda 环境中，开发者无法仅凭仓库内一个入口安装 Doctor、模型基准、桌面工具与 OCR 所需的全部 Python 依赖。项目需要一个与 venv、uv 和 Conda 环境管理方式解耦的根目录 `requirements.txt`，统一依赖版本、包索引与安装文档。

## What Changes

- 在仓库根目录新增唯一面向开发者的 `requirements.txt`，固定应用、GPU、图像、桌面控制、Windows UI Automation、PaddleOCR/PaddlePaddle 和测试运行所需的全部直接依赖。
- 在该文件中声明 CUDA 13.0 PyTorch wheel 所需的额外索引，使标准 `pip install -r requirements.txt` 能完成全部安装。
- 保留 `pyproject.toml` 作为包元数据和 `max-agent` 命令入口来源，但文档不再要求开发者组合多个 requirements 文件。
- 将 `requirements/base.txt`、`requirements/torch-cu130.txt` 和 `requirements/constraints.txt` 退出公开安装流程；是否删除这些旧文件由实现阶段在确认无内部引用后决定，避免形成多个相互漂移的依赖真源。
- 更新 `README.md`、`docs/week1/architecture-report.md`、`tech-design.md` 及其他相关说明，统一使用 `python -m pip install -r requirements.txt`；对 uv 使用 `uv pip install -r requirements.txt`，Conda 只负责创建/激活 Python 3.12 环境。
- 增加静态或自动化校验，确认统一清单包含 Doctor 和 benchmark 的直接导入依赖，并验证安装后的 `pip check`、单元测试与 CLI 帮助。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-bootstrap`：运行时准备从依赖预置环境和多个清单，改为通过根目录单一 `requirements.txt` 安装全部 Python 依赖，并支持 venv、uv 与 Conda 创建的 Python 3.12 环境。

## Impact

- 依赖与构建：新增根目录 `requirements.txt`，调整或移除 `requirements/` 下旧清单的公开职责，并可能补充依赖清单一致性测试。
- 文档：更新 `README.md`、`tech-design.md`、`docs/week1/architecture-report.md` 及引用旧安装流程的第一周文档。
- 开发流程：Conda `max` 仍是当前验证环境，但不再是安装依赖的前置条件；venv、uv 和其他 Conda 环境共享同一 pip-compatible 清单。
- 网络与平台：安装仍需访问 PyPI 和 PyTorch CUDA 13.0 wheel 索引；当前目标平台保持 Windows 11、Python 3.12 和 NVIDIA CUDA 13.0。
