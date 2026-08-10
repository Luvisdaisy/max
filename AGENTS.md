# MAX 仓库协作说明

## 文档语言

- 本项目后续新增或实质性更新的文档默认使用中文，包括 `README.md`、`docs/`、OpenSpec 工件和面向开发者的操作说明。
- 代码标识符、命令、配置键、文件路径和必要的第三方专有名词保持原样；其余说明文字使用中文。

## 项目背景

- 这是 Windows 本地 GUI Agent 原型。支持 Python 3.12；当前验证环境是名为 `max` 的 Conda 环境，但开发者也可使用 venv 或 uv 创建隔离环境。
- Python 项目采用 `src/` 布局。使用命令入口前，在仓库根目录执行 `python -m pip install -r requirements.txt`；该清单会安装全部直接依赖并以 editable 模式安装当前仓库。
- 下载的模型仅能存放在 `model/`；诊断与基准证据仅能存放在 `artifacts/`。两者均由 Git 忽略。
- 除非有独立且已批准的变更，否则桌面控制与模型驱动聊天均不在当前范围内。

## 代码风格

- 编码时优先选择简单、高效且直接的实现。
- 未有明确需求时，不引入 fallback、兼容分支或额外抽象。
- 能以一行清晰代码解决的问题，避免无必要地拆分为多行；但不得以牺牲可读性、错误处理或正确性为代价。

## 代码注释规范

- 所有新增或修改的代码都必须具备完善的中文注释；注释应覆盖模块职责、公开接口、关键数据结构、复杂业务规则、边界条件，以及非直观的实现或性能、安全决策。
- 注释应解释“为什么”与约束条件，不重复代码本身显而易见的操作；代码逻辑、接口或行为变更时，必须同步更新受影响的注释，避免过期或误导性说明。
- 不得为满足形式要求添加无信息量的逐行注释；对简单且语义自明的代码可保持简洁，但涉及重要逻辑时应确保阅读者无需反推意图。

## 未来工具目录约定

- Agent 编排器是唯一推进任务状态的核心；感知、模型、安全、桌面执行、验证、恢复和归档能力均通过工具/插件契约提供。
- 新增感知实现时必须置于 `src/max_agent/tools/perception/`，不得新增顶层 `perception` 包；`tools/registry.py` 是编排器调用工具的唯一入口。
- 不为尚未实现的能力创建空包或占位工具。

## 常用验证命令

```powershell
python -m unittest discover -s tests -v
python -m pip check
max-agent doctor --artifact-root artifacts
```

若激活 Conda 后找不到 `max-agent`，使用 `python -m max_agent.cli`，或将 `$env:CONDA_PREFIX\Scripts` 添加到当前会话的 `PATH`。

## 技术报告同步

- 根目录 `tech-design.md` 是系统技术设计报告。涉及公开命令、模块职责、数据归档、安全边界或已实现能力的代码变更，必须同步更新该报告。
- 报告必须区分“当前已实现基线”和“后续设计/路线图”；不得删除未实现的设计内容，除非变更明确废弃该设计。
- 更新后应以当前代码、自动化测试和实际命令输出核对报告中的已实现行为，避免把计划能力表述为已交付。

## OpenSpec 工作流

- 本项目不依赖全局安装的 `openspec` 命令。必须在仓库根目录使用以下前缀调用 OpenSpec：

  ```powershell
  npx.cmd --yes @fission-ai/openspec@1.8.0 <子命令>
  ```

  例如：

  ```powershell
  npx.cmd --yes @fission-ai/openspec@1.8.0 status
  npx.cmd --yes @fission-ai/openspec@1.8.0 new change <change-name>
  npx.cmd --yes @fission-ai/openspec@1.8.0 instructions apply --change <change-name> --json
  npx.cmd --yes @fission-ai/openspec@1.8.0 validate --specs
  ```

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
