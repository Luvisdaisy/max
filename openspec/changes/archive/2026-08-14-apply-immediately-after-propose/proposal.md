## Why

当前 `openspec-propose` 在产物齐了之后会停下来，等用户再发 `/opsx:apply`。这多一轮确认没有新信息，拖慢实现。用户要求：提案写完后同一轮直接实现。

## What Changes

- 标准流程改为：`propose` 的 `applyRequires` 产物完成后，同一轮立刻 `apply`，不要停下来等人发实现指令。
- 更新 `AGENTS.md` 与 `.agents/skills/openspec-propose/SKILL.md`。
- 需求仍不清、或提案与口头要求冲突时，仍先问再做；不把「写完提案」当成又一次审批关卡。

## Capabilities

### New Capabilities

- `openspec-workflow`：本仓库 OpenSpec 提案与实现的衔接约定。

### Modified Capabilities

- （无）

## Impact

- `AGENTS.md` 标准流程
- `.agents/skills/openspec-propose/SKILL.md`
- 助手行为：提案完成后继续按 `tasks.md` 实现
