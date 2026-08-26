## 1. 输出契约

- [x] 1.1 更新 GUI system 提示，移除正文 JSON、`thought` 和文本工具调用要求，写明普通对话与 GUI 任务的简洁回复规则。
- [x] 1.2 保留现有原生工具调用、独立 reasoning 流与桌面核验约束，不新增正文解析分支。

## 2. 回归验证

- [x] 2.1 补充提示词与 Agent 测试，验证身份询问不要求 JSON／内部思考，GUI 工具调用仍通过 native `tool_calls`。
- [x] 2.2 运行 `uv run ruff format src tests`、`uv run ruff check src tests` 与相关 pytest 用例。
