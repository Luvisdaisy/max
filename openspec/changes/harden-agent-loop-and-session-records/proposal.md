## Why

会话 `20260829-174928` 在一次简单的浏览器搜索中执行了 52 次循环：模型反复把逻辑坐标当作视图像素、重复进行无结果定位，最后虽完成任务，却暴露了循环恢复策略不足。当前 `task_complete` 还会在同一观察轮中直接把模型声明视为已验证，且会话把消息历史完整复制进 checkpoint，既削弱完成证据的可信度，也使本地 JSON 随历史线性膨胀。

现在需要将可恢复错误转化为明确的循环护栏，并让会话文件成为高效、可独立审计的任务记录。

## What Changes

- 为视图坐标越界、重复定位未命中和重复工具失败增加有界恢复策略，阻止同类无效动作持续消耗迭代次数。
- 将完成流程改为“完成声明—后置观察—独立核验”：`task_complete` 不再直接把任务标为已验证。
- 为每次运行把终态原因及紧凑汇总写入会话，使单个会话可识别正常完成、迭代上限、推理失败和中断，并关联运行事件中的模型结束原因与用量。
- 将 checkpoint 改为仅保存可恢复执行状态与消息游标，消息历史只在会话顶层保存一次；大型定位观察改为按帧引用和摘要，避免重复写入。
- 保持对既有会话 JSON 的兼容加载；新格式不迁移或改写旧会话。

## Capabilities

### New Capabilities

- `agent-recovery-guardrails`: 将坐标、定位与重复失败转化为可解释且有界的 ReAct 恢复策略。
- `completion-evidence-verification`: 对桌面副作用任务的完成声明实施独立的后置观察与证据核验。
- `efficient-session-checkpointing`: 以消息单一事实源、游标式 checkpoint 和紧凑运行摘要持久化会话。

### Modified Capabilities

- `react-agent`: 调整循环终止、失败恢复与完成验证的状态机契约。
- `session-store`: 调整 checkpoint、观察引用和运行终态摘要的会话 JSON 契约。
- `run-observability`: 让模型结束原因与最终诊断汇总可被会话引用。

## Impact

- 受影响代码：`src/max_gui/agent/graph.py`、`context.py`、`prompts.py`、`state.py`、`src/max_gui/session/store.py`、`src/max_gui/observability/`，以及定位与会话测试。
- 对外影响：新会话 JSON 的 checkpoint 不再包含完整消息副本；调用方继续从顶层 `messages` 读取历史。旧 JSON 仍可读。
- 不新增服务、数据库或第三方依赖；继续使用本地 JSON/JSONL 和现有截图文件。
