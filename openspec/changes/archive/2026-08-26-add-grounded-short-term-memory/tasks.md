## 1. 任务事实模型与持久化

- [x] 1.1 在 `agent/context.py` 定义有上限的已落地事实结构、恢复过滤、去重与脱敏摘要逻辑。
- [x] 1.2 在新任务、续跑 checkpoint 与新用户任务边界初始化或恢复 `grounded_facts`，保证旧 JSON 安全降级且不跨任务继承。
- [x] 1.3 补充 `session-store` 测试：事实持久化、旧格式降级、坏条目过滤与新任务清空。

## 2. 工具结果与截图生命周期

- [x] 2.1 在 Agent 工具执行路径中仅从当前帧可执行 `locate` 结果提取标签、`target_id`、来源截图和状态，拒绝历史图、带框副本、失败及空结果。
- [x] 2.2 在成功截图、定位、移动、破坏性动作、失败与中断边界更新或失效事实，并保持与 `locate_hits` 和现有光标门禁一致。
- [x] 2.3 补充桌面与定位测试：新截图后旧编号和摘要均不可用，观察专用定位不建立事实，移动后生成光标核验事实。

## 3. 模型上下文与提示词

- [x] 3.1 将有效事实的受限摘要接入任务用户消息，保持近期工具调用链与现有上下文上限不变。
- [x] 3.2 更新 GUI 系统契约：有效定位优先 `mouse_move(target_id)`，无有效定位才 `locate`，移动后依据回注图决定无坐标点击。
- [x] 3.3 补充 Agent 测试：裁剪旧调用链后仍能看到有效事实，失效事实不进入请求，摘要不泄露逻辑坐标、OCR 或键盘正文。

## 4. 回归验证

- [x] 4.1 运行 `uv run ruff format src tests` 与 `uv run ruff check src tests`。
- [x] 4.2 运行 `uv run pytest tests/test_agent.py tests/test_tools.py tests/test_locate.py tests/test_session_store.py -q`，并修复本变更引入的失败。
