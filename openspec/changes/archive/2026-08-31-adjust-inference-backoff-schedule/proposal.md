## Why

当前主推理重试的基础等待从 0.5 秒开始，在限流或服务短暂不可用时过于激进，容易在同一限流窗口内连续发送后续请求。需要提高初始等待，并保持已有随机抖动、服务端等待优先和可中断语义。

## What Changes

- 将第 1–5 次重试的指数退避基础等待改为 2、4、8、16、32 秒。
- 保留每次最多为基础等待 20% 的随机正向抖动。
- 保持合法 `Retry-After` 优先和等待期间可中断的既有行为，并将单次等待上限提高至 40 秒。
- 更新推理重试的规格、实现和自动化测试中的预期值。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `inference-retry`：调整主推理请求在未产生流式输出时的指数退避基础等待序列。

## Impact

- 影响 `src/max_gui/inference/retry.py` 的等待计算。
- 影响 `tests/test_inference.py` 的退避时间断言。
- 不改变重试次数、错误分类、请求载荷、随机抖动比例、`Retry-After` 优先级或运行时配置接口。
