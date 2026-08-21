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

系统 MUST 列出已存会话（id、title、updated_at），并 MUST 能把当前 TUI 会话切到指定 id，加载该会话消息。切换会话 MUST NOT 改变进程内已加载的推理后端与 `MODEL_NAME`。

#### Scenario: 列出会话

- **WHEN** 用户执行 `/sessions`
- **THEN** TUI 展示已存会话的标题与时间戳

#### Scenario: 切换会话

- **WHEN** 用户选择一个已存在的会话 id
- **THEN** 记录区替换为该会话消息，后续回合追加到对应 JSON 文件，当前推理模型仍为配置中的 `MODEL_NAME`

### Requirement: 多模态消息载荷

已存消息 MUST 保留文本与图像引用（本地路径或编码引用），以便恢复会话时重建附件展示。缺失的图像文件 MUST 不阻止其余会话内容加载。

#### Scenario: 带图像引用恢复

- **WHEN** 会话中有带图像附件的用户消息，且文件仍存在
- **THEN** 重新加载后该消息仍显示图像附件

#### Scenario: 图像文件缺失

- **WHEN** 已存图像路径不再存在
- **THEN** 会话仍能加载，该消息显示缺失附件占位

### Requirement: 独立的桌面自动批准开关

会话 JSON MUST 仍持久化 `auto_approve` 与 `auto_approve_desktop`，缺省为 `false`，二者分开读写。缺少字段的旧会话 MUST 视为 `false` 且仍能加载。这两个字段 MUST NOT 再作为工具是否执行的依据。

#### Scenario: 新会话仍写入字段

- **WHEN** 系统创建新会话
- **THEN** 会话 JSON 中 `auto_approve` 与 `auto_approve_desktop` 为 `false`

#### Scenario: 旧会话缺字段仍可加载

- **WHEN** 已存会话 JSON 没有 `auto_approve_desktop`
- **THEN** store 成功加载该会话

### Requirement: 推理失败写入会话错误

当 `think` 因推理客户端异常结束时，会话 JSON 的 `status` MUST 为 `error`，MUST 写入可读错误说明，检查点 MUST 反映当时已提交的消息。MUST NOT 把上一回合的 `done` 与过期检查点留在磁盘上假装本回合成功。

#### Scenario: 多轮后推理 400 落盘

- **WHEN** 本回合已执行若干工具，下一轮 `think` 收到推理服务非 2xx
- **THEN** 保存后的会话 `status` 为 `error`，`error` 或检查点中含状态码或正文摘要，消息列表含已执行的工具结果

### Requirement: 持久化桌面视图坐标系

会话 JSON MUST 持久化最近一次成功 `screenshot` 的视图坐标系（原点、逻辑宽高、视图宽高、截图路径）。缺字段的旧会话 MUST 仍能加载，并视为尚无截图。加载会话后，后续桌面鼠标工具 MUST 使用该坐标系，直到下一次成功截图覆盖。

#### Scenario: 截图后写入会话

- **WHEN** 一次成功 `screenshot` 结束并保存会话
- **THEN** 该会话 JSON 含有视图坐标系字段，再次打开同一会话后鼠标工具按视图像素换算

#### Scenario: 旧会话缺字段

- **WHEN** 已存会话 JSON 没有视图坐标系字段
- **THEN** store 成功加载，鼠标工具视为尚无截图

### Requirement: 持久化文字定位命中表

会话 JSON MUST 持久化最近一次成功 `ocr_locate` 的编号到逻辑中心映射。缺字段的旧会话 MUST 视为空表。下一次成功定位 MUST 覆盖旧表。

#### Scenario: 定位结果可恢复

- **WHEN** 会话保存时已有 `id=1` 的定位中心
- **THEN** 重新加载后 `mouse_click` 的 `target_id=1` 仍指向同一逻辑中心

### Requirement: 工具消息持久化执行元数据

`role` 为 `tool` 的会话消息 MUST 在 `content` 中保存工具名 `name` 与嵌套对象 `exec`。`exec` MUST 至少包含：`iteration`、`subtask`（无计划时为 `null`）、`arguments`（可 JSON 序列化的短对象；过长 MUST 截断）、`duration_ms`、`error`（无错误为 `null`）、`has_image`。MUST NOT 把图像字节或 base64 写入 `exec`。MUST NOT 另写 `artifacts/runs/` 执行日志。缺少 `exec` 的旧会话 MUST 仍能加载。发给模型时 MUST NOT 把 `exec` 编进请求正文。

#### Scenario: 截图写入 exec

- **WHEN** Agent 成功执行一次 `screenshot` 并保存会话
- **THEN** 对应 tool 消息 `content.name` 为 `screenshot`，`content.exec.has_image` 为真，`content.exec.error` 为 `null`，且项目下不因此创建 `artifacts/runs/` 文件

#### Scenario: 工具错误仍写入 exec

- **WHEN** 工具返回错误文本或业务失败
- **THEN** 该 tool 消息 `content.exec.error` 为非空字符串，且会话仍保存该条消息

#### Scenario: 旧会话缺 exec

- **WHEN** 已存 tool 消息没有 `exec` 字段
- **THEN** store 成功加载该会话

### Requirement: 助手消息可带思考原文

会话 JSON 中 `role=assistant` 的 `content` MUST 允许可选字符串字段 `reasoning`。缺少该字段的旧消息 MUST 仍能加载。重新打开会话时，若存在 `reasoning`，记录区 MUST 能展示这段思考（与正文分区）。编码发给模型时 MUST NOT 把 `reasoning` 作为助手 `content` 正文。

#### Scenario: 带思考字段恢复

- **WHEN** 已存助手消息含非空 `reasoning` 与 `text`
- **THEN** 重新加载后记录区可见该思考文本，且后续 think 请求的该条助手消息正文不含 `reasoning` 字符串

#### Scenario: 旧消息缺字段

- **WHEN** 已存助手消息没有 `reasoning`
- **THEN** 会话仍能加载，记录区只展示原有正文

### Requirement: 消息按节点增量写入

在同一用户回合内，助手消息与 tool 消息 MUST 在对应节点完成时写入会话文件，各自 `created_at` MUST 为该次写入时刻。MUST NOT 把同一回合全部消息拖到图结束再用同一个时间戳一次性写入。

#### Scenario: 工具循环中途时间戳已不同

- **WHEN** 助手先请求工具、随后 tool 结果写入
- **THEN** 会话 JSON 中该 tool 消息的 `created_at` 不早于对应助手消息的 `created_at`

### Requirement: 会话 model 字段不覆盖运行时配置

创建会话时 MUST 把当时配置中的 `MODEL_NAME` 写入会话 JSON 的 `model` 字段作为盖章。列出或切换会话 MUST 加载该会话消息，MUST NOT 根据会话内 `model` 修改当前 `Settings` 的 provider 或 `MODEL_NAME`。后续推理 MUST 仍使用启动时从 `.env` / 环境变量加载的模型。

#### Scenario: 切换旧会话不改推理模型

- **WHEN** 当前配置 `MODEL_NAME` 为 `qwen3.5-4b`，用户切换到 `model` 字段为其它值（含历史短别名）的已存会话
- **THEN** 记录区显示该会话消息，但随后的 think 请求仍使用 `qwen3.5-4b`

#### Scenario: 新会话盖章当前模型名

- **WHEN** 用户提交 `/new` 且当前 `MODEL_NAME` 为 `Qwen/Qwen3.8-27B`
- **THEN** 新建会话 JSON 的 `model` 为 `Qwen/Qwen3.8-27B`
