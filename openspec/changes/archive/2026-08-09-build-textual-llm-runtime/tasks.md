## 1. 本地 LLM 运行时

- [x] 1.1 定义会话内本地文本运行时契约及状态（未加载、加载中、就绪、失败），复用固定 Qwen3.5-2B 本地目录和离线完整性预检。
- [x] 1.2 实现 Qwen3.5-2B 的纯文本懒加载与生成，确保模型和 processor 仅从本地解析、同会话复用且不触发网络访问；Qwen3.5-4B 留作后续容量验证。
- [x] 1.3 将模型缺失、CUDA/BF16 不可用、OOM 与生成错误映射为不含绝对路径的可操作运行时错误。
- [x] 1.4 为运行时的首次加载、复用、预检失败和生成失败添加不使用真实 GPU 模型的单元测试。

## 2. Textual 交互界面

- [x] 2.1 重构 Textual 应用以显示聊天记录、用户输入、模型加载/生成状态和可恢复错误。
- [x] 2.2 在 Textual worker 中串行执行普通文本生成，防止加载或生成时冻结界面及并发重入。
- [x] 2.3 将 `/doctor` 接入现有诊断与归档核心，并保留 `/quit` 和未知 slash command 的会话行为。
- [x] 2.4 为 Textual 的启动、普通消息状态、slash command 分发和运行时错误增加应用级测试。

## 3. 启动入口与依赖收敛

- [x] 3.1 将 `max-agent` 与 `max-agent --chat` 实现为同一 Textual 启动路径；使其他旧选项和子命令返回用法错误且不执行操作。
- [x] 3.2 删除不再使用的 Typer、Rich、Prompt Toolkit CLI/前端代码及其测试，保留 packaging 的 `max-agent` 入口点，以及下载、元数据校验和基准的非公开实现模块。
- [x] 3.3 在确认无直接引用后，从 `pyproject.toml` 与 `requirements.txt` 移除 Typer、Rich、Prompt Toolkit，保留 Textual 及本地模型运行所需依赖。
- [x] 3.4 更新 CLI、依赖清单和运行时契约测试，覆盖两个支持入口和所有已移除入口的拒绝行为。

## 4. 文档与验证

- [x] 4.1 更新 `README.md`，声明破坏性启动入口变更、Textual 使用方式、`/doctor`、本地模型前置条件及离线失败边界。
- [x] 4.2 更新 `tech-design.md` 的当前实现基线，区分已交付的 Textual/本地 LLM 运行时与未实现的桌面 Agent 路线图。
- [x] 4.3 使用 Qwen3.5-2B 运行完整单元测试、`python -m pip check`、`max-agent --help`、Textual 交互式冒烟检查、OpenSpec 变更验证和 `git diff --check`；如本机显存不足，记录加载失败证据而不伪造生成结果。
