# AGENTS.md

面向在本仓库工作的 AI 助手与贡献者。本文件是项目级约束，优先级高于通用习惯。

## 项目是什么

`max-gui` 是基于本地模型的多模态 ReAct GUI Agent CLI。已落地：Textual REPL、LangGraph ReAct、OpenAI 兼容 vLLM 客户端（开发默认 `model/qwen3.5-2b`）、工作区文件/搜索/沙箱 Python 工具、PyAutoGUI 桌面工具（截图回注、移鼠、点按、拖拽、`keyboard_type` / `keyboard_press`），以及 `artifacts/sessions/` 下按时间戳命名的 JSON 会话。桌面调研记录见 `docs/gui-tools.md`。

## 语言

- 与用户的全部对话使用中文。
- 仓库内所有文档使用中文：`README.md`、`openspec/` 下的 proposal / design / specs / tasks、注释性设计说明、变更记录。
- 代码标识符（模块名、函数名、变量名、commit type）使用英文。
- Git 与 GitHub 操作一律使用英文：commit message、PR 标题与正文、branch 名、tag、release note。
- 用户可见文案（TUI、错误提示、帮助）使用中文，除非用户另有要求。

## 必须使用 OpenSpec

本项目按 OpenSpec 规范开发。没有对应 change 的实现视为不合规。

标准流程：

1. **探索**（可选）：需求不清时用 `openspec-explore`，先对齐再写变更。
2. **提案**：用 `openspec-propose` 生成 change，至少包含 `proposal.md`、`design.md`、`specs/`、`tasks.md`。
3. **实现**：用 `openspec-apply-change` 按 `tasks.md` 逐项实现，完成后立刻把对应任务标为 `[x]`。
4. **归档**：实现完成后用 `openspec-archive-change` 归档到 `openspec/changes/archive/`。禁止删除变更记录。归档后立刻同步更新项目级说明文件，但不额外需要记录具体的归档信息。

约束：

- 新功能、行为变更、破坏性改动、架构调整：必须先有 `openspec/changes/<change-name>/`。
- 实现过程中发现设计不对：先改 OpenSpec 产物，再改代码，不要只改代码。
- 纯笔误、格式化、依赖锁文件等无行为变化的修补，可不开 change；除此之外不要绕过 OpenSpec。
- 开发记录必须留在仓库里：`openspec/changes/`（进行中）与 `openspec/changes/archive/`（已完成）。不要用聊天记录代替归档。
- 每次 OpenSpec 归档完成后，必须同步更新项目级说明文件（至少 `AGENTS.md`、`README.md`，以及本次变更实际影响的其他说明），使其与已落地的能力、流程和约束一致。不要只归档 change、不改对外说明。

相关技能：`.agents/skills/openspec-propose/`、`openspec-apply-change/`、`openspec-archive-change/`、`openspec-explore/`。

## 先问再做

信息不完整时先问用户，不要自行补全需求。

必须停下来询问的情况：

- 需求、范围、验收标准不清楚
- 存在多种合理实现，且选择会影响对外行为或架构
- OpenSpec 产物与用户最新口头要求冲突
- 缺少运行所需的密钥、模型路径、服务地址等环境信息
- 任务可能删除数据、改动公开接口、或扩大到未请求的模块

提问时说明卡在哪一点、已知选项、以及你建议选哪个。得到答复前不要按猜测继续实现。

## 保持简单

能一行解决的问题，不要拆成新抽象、新模块或新框架。

- 改动范围以当前任务为界，不做顺手重构。
- 只有在消除真实重复、或仓库里已有同样模式时，才引入新抽象。
- 优先使用仓库已有的库、目录结构和命名。
- 不要为假设中的未来需求预留扩展层。

## Git 提交

使用 [Conventional Commits](https://www.conventionalcommits.org/)：

```
<type>(<scope>): <description>
```

- `type`：`feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `perf` / `ci`
- `scope` 可选，用短英文模块名，例如 `tui`、`agent`、`tools`、`inference`、`session`、`openspec`
- `description` 必须用英文，一句话说明做了什么，不用句号结尾
- 破坏性变更加 `!`（如 `feat(agent)!: ...`），并在正文用英文写清 `BREAKING CHANGE:`
- PR 标题与正文必须用英文；标题可沿用 Conventional Commits，或 `[type] Description`
- 一个提交只做一件事；不要把无关文件塞进同一次提交
- 未经用户明确要求，不要提交、不要 `git push`

示例：

```
feat(tui): add streaming output and session history scrolling
fix(session): restore checkpoints after interrupt
docs(openspec): document agent-tools retry on failure
chore: add ruff and pytest config
```

## 编码规范

Ruff 是唯一的格式化与 lint 工具，配置在 `pyproject.toml` 的 `[tool.ruff]`。不要引入 Black、独立 isort 或 flake8。

- 行宽 100，双引号，4 空格缩进，换行用 LF。
- 代码标识符用英文；用户可见文案与文档用中文，中文标点保持全角。
- 公开函数与模块级 API 使用类型标注；测试夹具与一次性回调不必为过关而堆注解。
- 完成实现后必须运行：

```
uv run ruff format src tests
uv run ruff check src tests
```

- 只在规则误报或有意违反时写 `# noqa`，并写明规则码。不要为未启用的规则留 noqa。

## 实现时

- 先读相关 OpenSpec 产物和现有代码，再改文件。
- 用 `uv` 管理依赖与运行环境（Python `>=3.12`）。
- 测试覆盖随风险调整：局部改动保持小测试；跨模块或用户可见流程要补行为测试。
- 不要提交密钥、模型权重、本地会话数据库。
- 不要修改你未参与且与当前任务无关的已有改动。
