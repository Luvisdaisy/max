## ADDED Requirements

### Requirement: 仅加载用户授权的 Online-Mind2Web 任务数据

系统 SHALL 仅从用户显式指定的本地任务数据文件加载 Online-Mind2Web 任务。每条任务 MUST 含非空的
`task_id`、`website`、`task_description` 和正整数 `reference_length`；加载器 MUST 拒绝重复任务标识、
非法 URL 或缺失字段。系统 MUST NOT 自动下载任务数据、接受远端数据集访问条款，或从上游克隆示例推断
完整任务集。

#### Scenario: 缺少授权任务文件

- **WHEN** 用户未提供任务数据文件或指定路径不存在
- **THEN** 系统给出中文配置错误且不启动浏览器、不请求网络、不创建模型运行

#### Scenario: 加载合法任务数据

- **WHEN** 用户指定的任务文件含字段完整且标识唯一的任务
- **THEN** 系统加载原始任务字段，并把任务源路径与内容摘要写入本次 manifest

### Requirement: 安全清单和预检决定可执行任务

系统 SHALL 要求用户显式提供安全清单，清单 MUST 列出允许执行的 `task_id`、允许起始域、单题最大步骤数
和超时。运行前系统 MUST 为每条计划任务记录 `ready`、`site_unreachable`、`captcha_or_login`、
`unsafe_action_risk`、`task_stale` 或 `environment_error` 之一；只有 `ready` 任务可以进入 Agent 执行。

#### Scenario: 未列入安全清单的任务

- **WHEN** 任务存在于上游数据但其 `task_id` 不在安全清单
- **THEN** 系统将其记录为 `unsafe_action_risk`，不启动浏览器或 Agent

#### Scenario: 预检发现登录或验证码

- **WHEN** 起始页面要求登录、验证码或其它无法安全执行的身份验证
- **THEN** 系统记录 `captcha_or_login`，保留预检证据，且不将该任务计为模型失败
