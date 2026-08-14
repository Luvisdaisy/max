# react-agent Specification

## Purpose

LangGraph ReAct 循环、状态、JSON 检查点、中断恢复。

## Requirements

### Requirement: ReAct 状态机

Agent SHALL 用 LangGraph StateGraph 实现 `think`、`act`、`observe` 节点。一个回合 MUST 从 `think` 开始。若模型返回工具调用，图 MUST 先跑 `act` 再 `observe`，然后回到 `think`。若模型不再返回工具调用，图 MUST 以 `done` 结束。

#### Scenario: 纯文本完成

- **WHEN** 模型返回最终助手消息且无工具调用
- **THEN** 图状态为 `done`，且不调用任何工具

#### Scenario: 一次工具循环

- **WHEN** 模型返回工具调用且工具成功
- **THEN** 图执行 `act` 再 `observe`，追加工具结果，并再次调用 `think`

### Requirement: 迭代上限

Agent MUST 在单次用户回合中，于配置的最大 Think/Act/Observe 循环次数后停止。触达上限时，状态 MUST 为 `error`，记录 MUST 包含迭代上限说明。

#### Scenario: 达到最大迭代

- **WHEN** 模型在 `max_iterations` 轮之后仍继续请求工具
- **THEN** Agent 不再分发下一个工具，并向用户报告已达迭代上限

### Requirement: 中断与恢复

Agent MUST 接受来自 TUI 的中断。中断状态 MUST 写入该会话 JSON 中的检查点。恢复同一会话 MUST 从最近检查点恢复图状态，而不是从头重跑该回合，除非用户开始新回合。不得使用 SQLite 保存检查点。

#### Scenario: 运行中中断

- **WHEN** 用户在 `think` 或 `act` 期间中断
- **THEN** 状态变为 `interrupted`，检查点写入该会话 JSON

#### Scenario: 中断后恢复

- **WHEN** 用户在中断后继续同一会话
- **THEN** Agent 加载最近检查点并从该节点继续

### Requirement: 上下文包含工具结果

`observe` 之后，下一次 `think` 调用 MUST 包含此前的用户/助手消息以及本回合最新工具结果。

#### Scenario: 模型能看到工具输出

- **WHEN** `read_file` 返回文件内容
- **THEN** 随后的 `think` 模型请求把这些内容作为 tool 消息带上
