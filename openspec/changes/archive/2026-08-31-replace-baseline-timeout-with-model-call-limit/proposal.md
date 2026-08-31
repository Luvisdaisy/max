## Why

真实桌面任务需要同时限制墙钟占用和模型调用成本。原 180 秒窗口偏短，而完全取消时长上限又可能使慢请求长期占用
桌面，因此采用 5 分钟与 20 次逻辑模型调用的双重上限，并让所有任务使用同一套受控工具。

## What Changes

- **BREAKING** baseline 单题改为最多执行 5 分钟或 20 次执行 Agent 逻辑模型调用，以先到者为准。
- provider 内部重试和独立评审 AI 不计入 20 次额度；达到模型额度时记录 `model_limit`，达到时长上限时记录
  `timeout` 或 `timeout_forced`。
- 任一上限终止执行后均取得终态截图并自动进入独立评审。
- 所有 baseline 评审固定使用 Qiniu 注册配置，与执行 Agent 的 provider/model 隔离。
- 每题向执行 Agent 暴露当前工具注册表中除 `activate_app`、`click` 外的全部工具。
- baseline 启动时打印执行模型的 provider 和 model 名称。
- 删除 Terminal、Reminders、WeChat 的任务专用 guard，以及 violation 终态、结果字段和评分硬门槛。
- 保留每题开始前的用户窗口确认、工具自身参数校验和 Agent 通用执行约束。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `baseline-evaluation-evidence-reporting`: 使用 5 分钟或 20 次执行模型调用的双重上限，固定 Qiniu 评审，开放受控注册工具并移除 violation 判定。

## Impact

- 影响 `src/max_gui/agent/graph.py`、baseline 模型、评分、执行编排、测试和中文说明。
- 不新增依赖，不改变普通 TUI、Web benchmark、独立评审次数或 provider 重试策略。
- baseline 启动需要 `MAX_QINIU_KEY`；Qiniu 评审模型使用 provider 注册表中的 `z-ai/glm-5.3-flash`。
- 五题任务的 `timeout_seconds` 统一为 300，同时作为执行终止值和评分时间参考。
