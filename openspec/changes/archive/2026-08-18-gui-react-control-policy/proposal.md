## Why

现有 ReAct 图能调桌面工具，但 4B 在「裸 Function Calling」上跑：没有 GUI 系统契约、历史里每张截图都回注、点完不复检、8 轮硬停。没有这条控制策略，提示词和后续 LoRA 都无法对比。第一期只补协议与可观测性，不换模型、不训权重、不加工具。

## What Changes

- 每次 `think` 请求注入固定中文 GUI `system`（先截图、视图像素 / `target_id`、看不清再 OCR、破坏性动作一次一个、动作后复检）。`system` 不写入会话 JSON。
- 发给模型时只保留最近 2 张仍存在的截图为 `image_url`，更早截图改为路径与视图尺寸摘要。会话落盘仍保留全部图像路径。
- `max_iterations` 默认改为 20。不改 `max_model_len`。
- 在现有图上增加轻量 `plan` / `current_subtask`（提示词 + 状态字段 + 规则判定），不加独立 `plan` 节点。
- `mouse_click` / `mouse_drag` / `mouse_scroll` / `keyboard_type` / `keyboard_press` 成功后，把新截图附在同一条 tool 结果上。取消或失败不截。`mouse_move` / `screen_info` 不附。
- 每步工具结果写入会话 tool 消息的 `name` 与嵌套 `exec`（迭代、子任务、参数、耗时、错误、是否新图）。不写 `artifacts/runs/`。`exec` 不发给模型、不作为 TUI 正文。

不包含：数据集、LoRA、新桌面工具、独立 plan 节点、同屏熔断、工具自动重试、提高 `max_model_len`。

## Capabilities

### New Capabilities

- （无）

### Modified Capabilities

- `react-agent`：注入 GUI system、状态含计划字段、迭代上限默认 20、观察后用规则更新子任务。
- `multimodal-inference`：编码阶段只把最近 2 张图编成 `image_url`。
- `desktop-gui-tools`：变异动作成功后在同一条结果中附新截图。
- `session-store`：tool 消息持久化 `name` 与嵌套 `exec`。
- `tui-repl`：记录区对 tool 只展示 `text`，状态区不指向独立执行日志文件。

## Impact

- `src/max_gui/agent/`：system 组装、plan 解析、observe 规则、`max_iterations`。
- `src/max_gui/inference/client.py`：注入 system、裁剪历史图像。
- `src/max_gui/tools/desktop.py`：变异工具成功后截图回注。
- `src/max_gui/config.py`：默认迭代次数。
- `src/max_gui/app.py`：状态文案不含 `artifacts/runs/`。
- 测试：`tests/test_agent.py`、`tests/test_inference.py`、`tests/test_tools.py`；补会话 `exec` 与「第三张图不进请求」用例。
