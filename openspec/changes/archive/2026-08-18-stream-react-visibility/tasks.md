## 1. 推理流式思考通道

- [x] 1.1 `ChatDelta` 增加 `reasoning`；SSE 解析 `reasoning_content` / `reasoning`，不并入 `text`
- [x] 1.2 `InferenceClient.stream` 增加 `on_reasoning`；补测试：思考与正文分回调、无思考字段行为不变
- [x] 1.3 `to_chat_messages` 编码 assistant 时忽略 `content.reasoning`

## 2. Agent 进度与增量落盘

- [x] 2.1 `run` 增加 `on_reasoning` / `on_message`，每个节点进入时调用 `on_status`
- [x] 2.2 `think` 完成后立即追加助手消息并 `on_message`；`act` 每完成一个工具立即追加并 `on_message`
- [x] 2.3 图结束 `_persist` 不重复追加已写入消息；补测试：双工具时第一次完成后即可观察到消息、会话无重复条目

## 3. TUI 逐步展示

- [x] 3.1 `#live` 分区展示思考与正文；每次助手 `on_message` flush 一条记录并清空 live
- [x] 3.2 工具 `on_message` 立即写入记录区；状态栏映射思考中 / 执行工具 / 观察中
- [x] 3.3 恢复会话时展示 `reasoning`；缺字段旧消息不变
- [x] 3.4 补 TUI 测试：token 进 live、think 结束成一条助手、工具在回合结束前可见、两轮 think 两条助手、状态栏 acting

## 4. 收尾

- [x] 4.1 `uv run ruff format src tests` 与 `uv run ruff check src tests`
- [x] 4.2 相关测试通过
