## ADDED Requirements

### Requirement: 提案完成后同一轮实现

当助手用 OpenSpec 为一项已对齐的需求生成 change，且 `proposal.md`、`design.md`、`specs/`、`tasks.md` 均已齐备时，MUST 在同一轮对话中按 `tasks.md` 开始实现。MUST NOT 把「请运行 `/opsx:apply`」或「要不要开始实现」当作默认收尾。用户当轮明确要求只提案、不要改代码时，MUST 停止在提案。

#### Scenario: 默认衔接到实现

- **WHEN** 一项功能或行为变更的提案产物已经齐备，且用户没有要求先停在提案
- **THEN** 助手继续按 `tasks.md` 实现，并在完成后把任务标为 `[x]`

#### Scenario: 用户只要提案

- **WHEN** 用户明确说先不要改代码或只要提案
- **THEN** 助手写完产物后停止，不改实现代码
