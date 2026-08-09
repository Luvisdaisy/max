## Context

参见 `proposal.md`。现有 CLI 由 Typer 回调和子命令承载，默认启动 Prompt Toolkit，Textual 仅作为可选界面；`ModelProvider` 只有最小协议，现有 Qwen 加载器服务于单图基准。Textual、Transformers、PyTorch 和项目内 Qwen3.5-2B 已是现有环境的一部分；Qwen3.5-4B 的真实基准曾出现显存不足，因此本阶段不将其作为聊天运行时前提。

## Goals / Non-Goals

**Goals:**

- 以单一 Textual 会话替代所有当前公开 CLI 操作路径。
- 建立可注入、可单元测试的本地文本运行时，复用现有项目内模型目录和离线边界。
- 在模型加载和生成期间保持界面可用，清晰显示状态与失败。

**Non-Goals:**

- 不实现桌面控制、工具调用、视觉输入、对话持久化、流式 token 渲染、远程推理或模型下载。
- 不为 CPU 或其他模型提供兼容路径，也不绕过 Qwen3.5-2B 的完整性和 GPU 要求；Qwen3.5-4B 仅留作后续容量验证。
- 不记录聊天文本、模型权重或绝对模型路径到 Git 追踪文件。

## Decisions

### 1. 使用轻量启动器而非保留 Typer 命令树

`max-agent` 保持 packaging entry point，但入口函数只解析可选的 `--chat` 并启动同一个 Textual 应用；其余旧选项和子命令从 CLI 契约、依赖和测试中删除。下载、元数据校验与基准模块保留为非公开内部 API，不可由本阶段 CLI 调用。这样启动表面与用户指定的两个入口一致。

备选方案是保留 Typer 只隐藏子命令。它仍会保留不需要的公开行为和依赖，因此不采用。

### 2. 将运行时状态限制为会话内懒加载单例

Textual 应用通过一个会话运行时对象处理状态：未加载、加载中、就绪、失败。首条普通消息触发 Qwen3.5-2B 本地目录预检和 BF16 CUDA 加载；同会话后续消息复用模型与 processor。阻塞模型工作在 Textual worker 中执行，避免冻结 UI；状态改变回到 UI 线程渲染。

备选方案是启动时预加载。它会让打开界面失败或明显变慢，也会在用户只需 `/doctor` 时消耗 GPU，故不采用。

### 3. 运行时契约为纯文本、local-only

新的 Provider 实现接收文本历史和生成上限，以 `local_files_only=True` 使用本地 Qwen 及 tokenizer/processor；加载与生成异常映射为稳定的用户提示，不包含绝对路径。不会调用 ModelScope、HTTP 或桌面工具。

备选方案是复用单图 benchmark 的函数。该函数包含图像处理、基准归档与一次性执行职责，不能表达交互会话复用，因此不采用。

### 4. Doctor 是 Textual slash command

保留现有诊断核心和证据归档，但只通过 `/doctor` 调用。这样维持无输入安全边界，并满足仅有两个启动入口的限制。

## Risks / Trade-offs

- Qwen3.5-2B 仍可能因当前 GPU 资源无法加载 → 在 UI 中显示加载失败与关闭其他 CUDA 进程的提示，保留 `/doctor` 与 `/quit`；Qwen3.5-4B 的显存评估延后。
- Textual worker 与模型状态可能并发重入 → 禁用加载中发送或串行化普通消息，确保一个会话只执行一个加载操作。
- 移除旧命令会破坏脚本 → 在 README 标记为 breaking change，并以 Textual slash commands 替代可交互诊断。
- 无 GUI 终端或测试环境无法运行 Textual → 使用应用构造和运行时契约的单元测试；交互式冒烟测试仅在可用终端进行。

## Migration Plan

1. 建立本地文本 Provider、会话运行时和对应单元测试。
2. 重写 Textual UI 以显示会话状态并分发普通文本、`/doctor`、`/quit`。
3. 将 packaging 入口简化为仅接受默认和 `--chat`，移除旧 CLI 与依赖引用。
4. 更新统一依赖清单、README、技术报告和 OpenSpec 规格；运行测试、`pip check`、入口帮助与 Textual 冒烟验证。
5. 如 Textual 运行时无法稳定启动，回退到前一归档版本；不得在本变更中恢复 Prompt Toolkit 或网络模型回退。
