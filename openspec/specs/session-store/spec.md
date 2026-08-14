# session-store Specification

## Purpose

基于本地 JSON 的会话/历史持久化与多会话恢复。

## Requirements

### Requirement: 将会话持久化为本地 JSON

系统 MUST 把会话和消息存成 `artifacts/sessions/`（路径可配置）下的独立 JSON 文件。不得使用 SQLite 或其他嵌入式数据库。创建会话 MUST 写入一个以本地时间戳命名的文件（例如 `20260814-153045.json`），内容包含 `id`、`title`、`model`、`created_at`、`updated_at`。会话 `id` MUST 等于去掉扩展名的文件名。

#### Scenario: 首次启动创建会话

- **WHEN** 用户启动 TUI，未传 `--new`，且尚无既有会话
- **THEN** store 创建一个时间戳命名的 JSON 文件，消息列表为空

#### Scenario: 持久化用户与助手消息

- **WHEN** 一个回合结束
- **THEN** 该会话 JSON 中包含本回合的用户消息与助手消息

### Requirement: 恢复最近会话

除非传入 `--new`，启动 MUST 打开最近更新的会话，并把消息加载进记录区。

#### Scenario: 重启后恢复

- **WHEN** 用户退出后再次启动 `max-gui` 且未传 `--new`
- **THEN** 记录区显示上一会话的消息

#### Scenario: 强制新会话

- **WHEN** 用户启动 `max-gui --new`
- **THEN** 创建新的时间戳 JSON 文件，既有会话文件仍保留在 `artifacts/sessions/`

### Requirement: 列出并切换会话

系统 MUST 列出已存会话（id、title、updated_at），并 MUST 能把当前 TUI 会话切到指定 id，加载该会话消息。

#### Scenario: 列出会话

- **WHEN** 用户执行 `/sessions`
- **THEN** TUI 展示已存会话的标题与时间戳

#### Scenario: 切换会话

- **WHEN** 用户选择一个已存在的会话 id
- **THEN** 记录区替换为该会话消息，后续回合追加到对应 JSON 文件

### Requirement: 多模态消息载荷

已存消息 MUST 保留文本与图像引用（本地路径或编码引用），以便恢复会话时重建附件展示。缺失的图像文件 MUST 不阻止其余会话内容加载。

#### Scenario: 带图像引用恢复

- **WHEN** 会话中有带图像附件的用户消息，且文件仍存在
- **THEN** 重新加载后该消息仍显示图像附件

#### Scenario: 图像文件缺失

- **WHEN** 已存图像路径不再存在
- **THEN** 会话仍能加载，该消息显示缺失附件占位
