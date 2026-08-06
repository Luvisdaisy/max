# MAX 仓库协作说明

## 文档语言

- 本项目后续新增或实质性更新的文档默认使用中文，包括 `README.md`、`docs/`、OpenSpec 工件和面向开发者的操作说明。
- 代码标识符、命令、配置键、文件路径和必要的第三方专有名词保持原样；其余说明文字使用中文。

## 项目背景

- 这是 Windows 本地 GUI Agent 原型。使用名为 `max` 的 Conda 环境与 Python 3.12。
- Python 项目采用 `src/` 布局。使用命令入口前，先执行 `python -m pip install -e .` 安装当前仓库。
- 下载的模型仅能存放在 `model/`；诊断与基准证据仅能存放在 `artifacts/`。两者均由 Git 忽略。
- 除非有独立且已批准的变更，否则桌面控制与模型驱动聊天均不在当前范围内。

## 常用验证命令

```powershell
python -m unittest discover -s tests -v
python -m pip check
max-agent --diagnose --artifact-root artifacts
```

若激活 Conda 后找不到 `max-agent`，使用 `python -m max_agent.cli`，或将 `$env:CONDA_PREFIX\Scripts` 添加到当前会话的 `PATH`。

## OpenSpec 工作流

- 将 `openspec/specs/` 视为当前行为契约。
- 实现前，在 `openspec/changes/<change-name>/` 中创建 proposal、delta spec、design 与 tasks 等规划工件。
- 使用 `openspec-update-change` 修改规划。必须先向用户展示拟议修改并获得确认，才可写入规划工件。
- 使用 `openspec-apply-change` 实现已批准任务。仅在实现完成并通过与风险相称的验证后，才可勾选任务。
- 除非用户明确要求修正历史记录，否则不得编辑已归档的变更。

## 归档后的强制核验

每次 OpenSpec 归档后，结束任务前必须完成并报告以下事项：

1. 确认变更任务均已完成；若归档保留了用户批准的未完成任务，必须逐项说明。
2. 除非用户明确要求跳过，否则将变更 delta spec 同步到 `openspec/specs/`。
3. 执行 `openspec validate --specs` 并报告结果。
4. 判断归档是否改变公开命令、用户工作流、安装步骤或项目协作约定。用户可见变化更新 `README.md`；Codex 协作约定变化更新本 `AGENTS.md`。
5. 报告归档路径，以及是否已同步主规格。

不得依赖 hook 完成这些核验；这是代理必须执行的工作流步骤。
