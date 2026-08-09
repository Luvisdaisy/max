## 1. 统一依赖清单

- [x] 1.1 从当前已验证的 Python 3.12 `max` 环境核对应用、CUDA、图像、桌面、UIA、OCR 和数据契约直接依赖的发行包名称与精确版本
- [x] 1.2 创建根目录 `requirements.txt`，加入 PyTorch CUDA 13.0 extra index、全部精确直接依赖和 `-e .`，确保单条 pip-compatible 命令同时安装依赖与项目入口
- [x] 1.3 在全仓库迁移引用后删除 `requirements/base.txt`、`requirements/constraints.txt` 和 `requirements/torch-cu130.txt`，确认不存在旧清单引用

## 2. 依赖契约测试

- [x] 2.1 新增自动化测试，校验根清单包含受信 PyTorch 索引、editable 项目条目以及 Doctor、benchmark、桌面/UIA 和 OCR 所需的直接发行包
- [x] 2.2 校验依赖清单中的版本与项目当前支持的 Python/CUDA 约束一致，并确保旧分拆清单不再作为安装入口

## 3. 文档同步

- [x] 3.1 更新 `README.md`，分别给出 venv + pip、uv + `uv pip`、Conda + pip 的环境创建方式，并统一使用根目录 `requirements.txt`
- [x] 3.2 更新 `docs/week1/architecture-report.md` 和 `tech-design.md`，将完整依赖复现从“预配置 Conda 环境”调整为环境管理器无关的单清单安装契约
- [x] 3.3 搜索并更新其他引用旧 requirements 文件或 `python -m pip install -e .` 作为完整安装步骤的开发者文档，同时保留必要的包开发说明

## 4. 安装与回归验证

- [x] 4.1 在仓库根目录执行 `python -m pip install -r requirements.txt`，确认 pip 能解析统一清单并保留 CUDA 13.0 构建
- [x] 4.2 使用 uv 对统一清单执行兼容性解析或安装验证，确认 extra index 与 editable 项目条目可被消费
- [x] 4.3 运行 `python -m pip check`、完整单元测试、`max-agent --help` 和非输入 Doctor，并记录任何仅能在交互式 Windows 会话完成的验证边界
- [x] 4.4 执行 OpenSpec 变更校验和 `git diff --check`，确认规划、实现与文档没有不一致或格式错误
