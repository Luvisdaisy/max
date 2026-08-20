# openspec-workflow Specification

## Purpose

本仓库 OpenSpec 提案、实现与归档的衔接：产物齐备后默认停下，实现和归档都等用户明确提出后再执行。

## Requirements

### Requirement: 提案完成后默认停止

当助手用 OpenSpec 为一项已对齐的需求生成 change，且 `proposal.md`、`design.md`、`specs/`、`tasks.md` 均已齐备时，MUST 停止在提案，MUST NOT 在同一轮按 `tasks.md` 改代码，MUST NOT 归档。用户当轮明确要求实现时，MUST 再用 `openspec-apply-change` 落地。用户当轮明确要求归档时，MUST 再用 `openspec-archive-change` 归档。

#### Scenario: 默认停在提案

- **WHEN** 一项功能或行为变更的提案产物已经齐备，且用户没有要求实现或归档
- **THEN** 助手写完产物后停止，不改实现代码，不移动 change 目录

#### Scenario: 用户要求实现

- **WHEN** 用户明确说开始实现或使用 `/opsx:apply`
- **THEN** 助手按 `tasks.md` 实现，并在完成后把任务标为 `[x]`

#### Scenario: 用户要求归档

- **WHEN** 实现已完成且用户明确要求归档
- **THEN** 助手归档该 change，并同步更新项目级说明文件
