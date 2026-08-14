## Context

`openspec-propose` 技能在全部产物完成后要求提示用户运行 `/opsx:apply`。本仓库按 OpenSpec 开发，提案本身已经是实现合同，再等一轮没有收益。

## Goals / Non-Goals

**Goals:**

- 提案产物齐备后，同一轮按 `openspec-apply-change` 实现。
- 文档与技能文案不再把「等人发 apply」写成默认步骤。

**Non-Goals:**

- 不改 OpenSpec CLI。
- 不取消「需求不清先问」。
- 不自动归档；归档仍在实现完成后单独做。

## Decisions

1. **衔接写进 `AGENTS.md` 与 propose 技能。**  
   项目级约束以 `AGENTS.md` 为准；技能是执行细则。  
   - 备选：只改口头习惯。不采用：下次会话又会停在提案。

2. **用户明确说「只提案、先别改代码」时遵守。**  
   默认是 propose 后 apply；用户收窄范围时以当轮指令为准。

3. **归档仍不自动。**  
   实现完成可以提示可归档，但不在 propose 技能里串归档。

## Risks / Trade-offs

- [Risk] 提案有误却直接改代码 → 需求不清仍先问；实现中发现设计不对先改 OpenSpec 再改代码。
- [Risk] 用户只想看提案 → 当轮说「先不要实现」即可。

## Migration Plan

改文档与技能即可，无运行时迁移。

## Open Questions

无。
