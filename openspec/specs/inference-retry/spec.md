# inference-retry Specification

## Purpose
TBD - created by archiving change add-inference-retry-policy. Update Purpose after archive.
## Requirements
### Requirement: 主推理请求采用有界重试

主推理客户端 MUST 在一次逻辑模型调用的首次请求失败后最多重试 5 次，默认重试次数 MUST 为 5，总网络尝试次数 MUST NOT 超过 6。`MAX_GUI_INFERENCE_MAX_RETRIES` MUST 允许使用 0–5 的整数；0 MUST 禁用重试，超出范围或不是整数 MUST 在配置加载时给出可读错误。每次重试 MUST 重发同一 URL、headers 与 payload，MUST NOT 自动修改消息、图片、工具、模型或 provider。

#### Scenario: 默认最多重试五次

- **WHEN** 未配置重试次数且每次请求都发生可重试错误
- **THEN** 客户端先请求 1 次、再重试 5 次，并在第 6 次失败后停止

#### Scenario: 配置零次重试

- **WHEN** `MAX_GUI_INFERENCE_MAX_RETRIES=0` 且首次请求发生可重试错误
- **THEN** 客户端不再发起第二次请求并返回首次错误

#### Scenario: 非法重试次数

- **WHEN** 重试次数小于 0、大于 5 或不是整数
- **THEN** 配置加载失败并指出允许范围为 0–5

### Requirement: 按可恢复性分类推理错误

客户端 MUST 重试连接失败、连接/读取/写入/连接池超时、服务端提前断开，以及 HTTP 408、425、429、500、502、503、504。客户端 MUST 重试正文为空、不可读或只有通用客户端错误的不透明 HTTP 400，也 MUST 重试结构化正文明确表示模型加载、服务繁忙、临时不可用、上游不可达或上游超时的 HTTP 400。客户端 MUST NOT 重试鉴权失败、模型不存在、请求字段非法、上下文超限、图片非法、消息非法、工具或 schema 非法等可判定永久错误；其它未列出的 HTTP 状态默认 MUST NOT 重试。最终错误 MUST 保留最后状态码或网络原因和已重试次数，但 MUST NOT 暴露密钥或 Authorization。

#### Scenario: 服务暂时不可达后恢复

- **WHEN** 前两次连接失败且第三次返回合法流
- **THEN** 客户端返回第三次结果且不向调用方返回前两次异常

#### Scenario: 不透明四百错误后恢复

- **WHEN** 首次请求返回无正文 HTTP 400 且第二次请求成功
- **THEN** 客户端重试并返回第二次结果

#### Scenario: 工具 schema 错误不重试

- **WHEN** HTTP 400 正文明确指出工具 schema 非法
- **THEN** 客户端只发送一次请求并立即返回包含该正文摘要的错误

#### Scenario: 限流达到重试上限

- **WHEN** 所有请求均返回 HTTP 429
- **THEN** 客户端最多重试 5 次并返回最后一次 429 与重试耗尽摘要

### Requirement: 重试采用可中断的有界退避

第 1–5 次重试 MUST 使用基础值为 2、4、8、16、32 秒的指数退避，并加入不超过各自基础值 20% 的抖动。合法 `Retry-After` MUST 优先于基础退避，但单次等待 MUST NOT 超过 40 秒。等待期间 MUST 检查用户中断；中断后 MUST 取消剩余等待并且 MUST NOT 发起下一次请求。

#### Scenario: 指数退避有上限

- **WHEN** 连续 5 次失败且服务端没有 `Retry-After`
- **THEN** 五次重试使用 2、4、8、16、32 秒基础等待并只增加规定范围内的抖动

#### Scenario: 第五次抖动不被截断

- **WHEN** 第五次重试使用最大随机值且服务端没有 `Retry-After`
- **THEN** 等待 38.4 秒，既不低于 32 秒基础等待，也不被 40 秒上限截断

#### Scenario: 遵守服务端等待时间

- **WHEN** 可重试响应携带合法 `Retry-After: 45`
- **THEN** 下一次请求前采用不超过 40 秒的 40 秒服务端等待值

#### Scenario: 退避期间中断

- **WHEN** 客户端正在等待下一次重试且用户发出中断
- **THEN** 等待及时结束、没有新的网络尝试，并以中断结果返回

### Requirement: 流式增量构成重放边界

客户端只可在当前逻辑模型调用尚未产生任何有效正文、reasoning、工具调用片段、finish reason 或 usage 时重试。任一有效流式增量已经解析或通过回调暴露后，客户端 MUST NOT 自动重放请求；此后的断流 MUST 返回明确错误。失败尝试的局部正文和工具调用累加状态 MUST 在下一次尝试前清空，成功调用 MUST 只返回一次完整结果。

#### Scenario: 首个增量前断流可重试

- **WHEN** 首次连接在任何有效 SSE 增量前断开且第二次请求成功
- **THEN** 客户端重试并只返回第二次请求的内容

#### Scenario: 正文输出后断流不重试

- **WHEN** 客户端已回调一段正文后连接断开
- **THEN** 客户端不再发送请求，并报告已产生流式输出因而未自动重试

#### Scenario: 工具调用分片后断流不重试

- **WHEN** 客户端已解析一个工具调用分片后连接断开
- **THEN** 客户端不再发送请求，Agent 不执行不完整工具调用
