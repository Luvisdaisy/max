## Why

当前 WSL Ollama 已配置 256K 上下文并能完成基础 GUI 工具链，但 Agent 仍按固定工具链条数裁剪上下文、每轮暴露全部工具、连续执行同批副作用调用，并把“模型不再调用工具”直接视为完成。这些边界会造成不必要的 token 与图像开销，也无法从运行时强制保证每次副作用后先观察、再验证任务结果。

## What Changes

- 为主推理请求增加面向 256K Ollama 的 token 预算：显式保留输出和安全余量，按预算选择完整工具链，并在超预算时给出可诊断错误。
- 根据 Agent 当前阶段动态暴露工具；无有效画面时只开放初始观察工具，有画面后开放观察、定位与动作工具。
- 将工具分为只读与副作用两类；一次模型回复最多执行一个副作用工具，拒绝在同一观察上连续执行多个副作用。
- 在副作用后强制进入观察与验证；只有模型明确给出可机器识别的完成声明，且最近副作用已有后置截图，才把任务标记为 `done`。
- 为工具调用统一增加严格参数校验、`additionalProperties=false`、真实超时和结构化错误结果。
- 扩充运行事件，记录上下文预算、动态工具数量、验证结果与被拒绝的副作用调用，不记录正文、截图内容或键盘输入。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-config`：为 Ollama 暴露固定 262144 token 的推理上下文容量，并配置输出预留与安全余量。
- `multimodal-inference`：模型请求在编码前按上下文预算选择完整工具调用链，并报告预算诊断。
- `react-agent`：按阶段暴露工具、限制单轮副作用、强制副作用后观察，并增加显式完成验证门。
- `agent-tools`：工具具备只读／副作用元数据、严格 JSON Schema 参数校验、超时和结构化错误。

## Impact

- 受影响代码：`src/max_gui/config.py`、`provider.py`、`inference/client.py`、`agent/context.py`、`agent/graph.py`、`agent/state.py`、`tools/protocol.py`、`tools/registry.py` 及工具 schema。
- 受影响测试：推理、Agent、工具、会话恢复和可观测性测试；增加面向 256K Ollama 的预算与多副作用回归。
- 受影响文档：`.env.example` 与 `README.md` 的 Ollama 上下文和运行边界说明。
- 不新增依赖，不修改 WSL Ollama 服务，不提交或归档现有 OpenSpec change。
