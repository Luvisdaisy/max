## 1. Agent 模型额度与工具暴露

- [x] 1.1 为 `AgentRunner.run()` 增加默认关闭的完整注册工具暴露开关，开启时使用 `registry.names()` 生成模型 schema。
- [x] 1.2 增加 Agent 测试，验证完整工具开关覆盖全部注册工具且默认动态工具策略不变。
- [x] 1.3 为完整工具模式增加可选排除集合，并验证 schema 与 Act 允许集合都排除指定工具。

## 2. Baseline 执行编排

- [x] 2.1 baseline 每题把执行 Agent 的 `max_iterations` 覆盖为 20，并把迭代上限规范为 `model_limit` 终态。
- [x] 2.2 增加 300 秒执行时限、温和中断和 5 秒强制取消收尾；验证超时与 20 次额度均自动进入评审。
- [x] 2.3 删除任务专用 `_guard` 和 tool_guard 注入，改由工具步骤回调统计动作数量。
- [x] 2.4 启动时构造并校验固定 Qiniu 评审 settings，传给全部任务且不修改执行 settings，manifest 记录评审 provider/model。
- [x] 2.5 修复 GLM-5.3-Flash 强制思考参数：评审固定启用 thinking、使用 `reasoning_effort=low`，且不输出 reasoning。
- [x] 2.6 baseline 排除 `activate_app`、`click`，并在启动时打印执行 provider/model。

## 3. 数据模型、评分与说明

- [x] 3.1 删除 violation 状态、结果字段、评分字段和安全硬门槛，成功仅依据独立评审 `pass`，评分版本升级为 `baseline-score-v2`。
- [x] 3.2 更新 baseline 测试与 JSON 往返断言，覆盖无 violation 字段、20 次额度、固定 Qiniu 评审、受控工具和动作统计。
- [x] 3.3 更新 README 与 baseline 中文说明，明确 5 分钟或 20 次先到者终止、固定 Qiniu 评审、计数范围和评审行为。

## 4. 验证

- [x] 4.1 运行 Ruff format/check、baseline 与 Agent 相关测试、完整 pytest、OpenSpec strict 和 `git diff --check`。
  本次 Ruff、OpenSpec strict、差异检查与完整 pytest 326 项均通过。
