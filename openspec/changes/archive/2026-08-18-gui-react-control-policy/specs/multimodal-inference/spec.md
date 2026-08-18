## ADDED Requirements

### Requirement: 编码时注入系统消息

当调用方提供系统提示时，`to_chat_messages` MUST 把一条 `role=system` 的文本消息放在编码结果最前。若原始消息已经以 `system` 开头，MUST NOT 再插入第二条。未提供系统提示时行为 MUST 与原先一致。

#### Scenario: 带系统提示编码

- **WHEN** 调用方传入非空系统提示与一条用户消息
- **THEN** 编码结果第一条为 `system`，第二条为该用户消息

#### Scenario: 已有 system 不重复

- **WHEN** 原始消息第一条已是 `system` 且调用方仍传入系统提示
- **THEN** 编码结果仍只有一条 `system` 消息

## MODIFIED Requirements

### Requirement: 工具消息中的图像回注

当 tool 或 assistant 消息携带本地图像引用时，客户端 MUST 把**本请求中按出现顺序最靠后的、仍存在的至多两张**图作为 `image_url` 内容部件附加（经现有最长边 / 最大字节预处理）。同一条消息的文本摘要 MUST 作为文本部件保留。更早的图像引用 MUST 改为文本摘要（至少含路径；能得知视图宽高则一并写出），MUST NOT 再附加对应 `image_url`。缺失的图像文件 MUST 跳过且不阻止其余部件编码。纯文本 tool 消息 MUST 仍只发送文本。用户消息中的本地图 MUST 计入上述「最近两张」限额。

#### Scenario: 截图进入下一轮 think

- **WHEN** tool 消息内容包含文本摘要与一张存在的 PNG 路径，且该请求中没有更晚的其它图
- **THEN** 发给模型的该条消息同时包含文本部件和 `image_url` 部件

#### Scenario: 纯文本工具结果

- **WHEN** tool 消息内容是字符串且无图像引用
- **THEN** 请求中该条消息不含 `image_url` 部件

#### Scenario: 截图文件缺失

- **WHEN** tool 消息引用的图像路径不存在
- **THEN** 客户端仍发送文本摘要，且不因缺图失败

#### Scenario: 第三张历史截图不再编码为图像

- **WHEN** 请求中按顺序有三张仍存在的本地截图
- **THEN** 仅最后两张带 `image_url`，最早那张只保留含路径的文本摘要
