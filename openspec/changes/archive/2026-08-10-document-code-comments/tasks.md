## 1. 基础设施与运行时模块注释

- [x] 1.1 为 `artifacts.py`、`config.py`、`runtime_paths.py`、`providers.py` 与包初始化模块补充中文模块职责、公开接口及关键约束说明。
- [x] 1.2 为 `model_runtime.py`、`local_llm.py`、`model_download.py` 与 `benchmark.py` 补充模型生命周期、资源约束、异常边界和非直观实现的中文注释。
- [x] 1.3 为上述模块对应测试补充中文测试意图与关键断言说明，并核对注释与当前行为一致。

## 2. 命令行、诊断与控制台模块注释

- [x] 2.1 为 `cli.py`、`diagnostics.py`、`console_core.py` 与 `console_frontends.py` 补充命令、诊断流程、状态转换和平台约束的中文注释。
- [x] 2.2 为 `test_cli.py`、`test_diagnostics.py`、`test_console_core.py`、`test_runtime_config.py`、`test_runtime_paths.py` 与相关测试辅助文件补充中文场景说明。
- [x] 2.3 审查该功能域差异，确认没有修改可执行逻辑、配置值或断言语义。

## 3. 编排器与工具注册模块注释

- [x] 3.1 为 `orchestration/` 下全部 Python 模块补充编排图、状态模型、提示词边界及公开接口的中文注释。
- [x] 3.2 为 `tools/base.py`、`tools/registry.py` 及 `tools/__init__.py` 补充工具契约、注册入口和扩展边界的中文注释。
- [x] 3.3 为 `test_orchestration.py` 与相关工具测试补充中文测试目的、状态迁移和非直观断言说明。

## 4. 感知工具模块注释

- [x] 4.1 为 `tools/perception/` 下全部 Python 模块补充感知职责、输入输出、平台依赖、失败边界和关键算法选择的中文注释。
- [x] 4.2 为 `test_perception_tools.py` 补充中文场景、替身对象和关键断言说明。
- [x] 4.3 审查感知工具改动，确认注释没有扩大未实现桌面控制或模型驱动聊天的范围。

## 5. 技术文档与全量核验

- [x] 5.1 更新 `tech-design.md` 的当前已实现基线，说明代码注释覆盖范围、维护规则及其与路线图的边界。
- [x] 5.2 对照 `src/max_agent/` 与 `tests/` 的 Python 文件清单复核全覆盖，并人工审查中文注释的准确性、信息量和一致性。
- [x] 5.3 执行 `python -m unittest discover -s tests -v`、`python -m pip check` 与 `max-agent doctor --artifact-root artifacts`，记录验证结果。
- [x] 5.4 复查最终差异，确认没有运行行为、公开命令、依赖、配置或测试断言语义变更。
