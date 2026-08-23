## 1. 流式用量解析

- [x] 1.1 为 `ChatDelta` 增加可选用量字段（`prompt_tokens` / `completion_tokens` / `total_tokens`），并补中文文档
- [x] 1.2 流式请求在 `stream` 为真时发送 `stream_options.include_usage=true`
- [x] 1.3 解析 SSE payload 级 `usage`，接受 `choices` 为空的用量块；该块不触发正文或思考回调，也不当作补全失败
- [x] 1.4 拼装完整回复时以后一次完整 `usage` 为准；三项均缺则为未知，不得写成 0；仅缺 `total_tokens` 时用输入加输出
- [x] 1.5 补推理测试：请求含 `include_usage`、空 choices 用量块、无 usage 时为未知、正文流式行为不变

## 2. 运行事件与累计

- [x] 2.1 `model.completed` 在用量已知时写入三项非负整数；未知时省略或 `null`，不得写 0；不复制正文或 reasoning
- [x] 2.2 `RunRecorder` 只累计已知用量，终态事件带累计值；全程未知则三项省略或 `null`
- [x] 2.3 从既有 JSONL 恢复时按同样规则重算累计，后续已知调用继续累加
- [x] 2.4 补记录器与 Agent 测试：两次调用累加、未知不记零、恢复后续加、成功调用写入用量且不含原文

## 3. TUI 监控面板

- [x] 3.1 监控面板增加用量行：已知时为「用量：输入 N / 输出 M / 合计 T」，否则为「用量：未知」，不得用 0 表示未知
- [x] 3.2 终态事件用记录器汇总覆盖面板累计，避免把同一运行的用量加两遍
- [x] 3.3 最近事件中模型完成摘要含当次输入与输出，当次未知则写「用量未知」；会话记录区不新增用量行
- [x] 3.4 补 TUI 行为测试：面板累计、未知文案、最近事件、记录区不受污染

## 4. 说明与质量

- [x] 4.1 更新 README：监控面板展示 token 用量，提供方未回传时显示未知
- [x] 4.2 运行 `uv run ruff format src tests` 与 `uv run ruff check src tests`，修复本次引入的格式与 lint 问题
- [x] 4.3 运行相关定向测试与 `uv run pytest`，确认推理、运行事件、TUI 与既有 Agent 行为通过
