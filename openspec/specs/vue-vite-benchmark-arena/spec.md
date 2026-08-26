# vue-vite-benchmark-arena Specification

## Purpose
TBD - created by archiving change refactor-vue-vite-benchmark-arena. Update Purpose after archive.
## Requirements
### Requirement: Vue + Vite 单进程评测场

系统 SHALL 使用 Vue + Vite 构建 Agent 可见的本地评测场。`max-gui --benchmark` MUST 只启动一个绑定
`127.0.0.1` 的 FastAPI 进程来托管构建产物、业务 API 和评测控制 API；运行时 MUST NOT 依赖 Vite
开发服务器或访问外网。

#### Scenario: 通过单一入口打开构建后的评测场

- **WHEN** 用户执行 `max-gui --benchmark` 并在浏览器打开回环首页
- **THEN** 浏览器加载 Vue 构建的首页，且 10/100 条启动、业务页面和评测控制接口均由同一 FastAPI 进程提供

### Requirement: Agent 可见业务交互与受限控制面隔离

系统 SHALL 提供可通过普通鼠标、键盘和滚轮完成的 Vue 业务页面及可见反馈。业务 API MUST NOT 返回
成功断言、任务指令或 `/api/state` 的评分状态；重置和评分接口 MUST NOT 出现在页面链接、菜单或可见文案中。

#### Scenario: Agent 仅经可见 UI 完成任务

- **WHEN** 运行器打开某条任务的业务页面
- **THEN** Agent 只能使用截图和键鼠执行页面提供的交互，而运行器独立读取不可见的评分状态

### Requirement: 统一起始页与可点击站内导航

评测场 SHALL 提供工作台、收件箱、项目、任务、日历、自动化、团队、报表和设置页面。每条任务 MUST
从 `/arena/home` 开始，页面切换 MUST 由 Agent 点击可见导航、面包屑或实体链接完成；运行器 MUST NOT
直接打开任务目标路由。后端 MUST 记录经可见导航产生的访问检查点，地址栏直接跳转不得满足该检查点。

#### Scenario: 跨页任务通过导航完成

- **WHEN** Agent 从统一起始页执行需要修改项目任务的工作流
- **THEN** Agent 点击站内导航进入项目和任务页面，评分状态记录对应导航检查点及最终业务修改

### Requirement: 旧版评测场不再可用

系统 MUST 删除服务器拼接的旧版业务 HTML、旧版业务页面路由与 `web-gui-v1` 任务文件，且 MUST NOT
保留兼容入口或复制展开逻辑。

#### Scenario: 旧任务和路由被拒绝

- **WHEN** 运行器或浏览器请求旧版任务集或旧版业务路由
- **THEN** 系统不加载、重定向或兼容执行旧版内容，并只接受 v2 评测场的任务与路由

