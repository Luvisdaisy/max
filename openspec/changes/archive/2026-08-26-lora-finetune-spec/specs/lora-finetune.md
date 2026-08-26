## ADDED Requirements

### Requirement: LoRA 微调提升 GUI 任务能力
多模态 ReAct GUI Agent SHALL 通过 LoRA 微调显著提升在屏幕理解、子任务规划和桌面工具调用上的准确率。

#### Scenario: 微调前后对比
- **WHEN** 使用预处理后的 ScreenAgent 数据集进行 LoRA 微调
- **THEN** 微调后模型在 GUI 任务成功率和动作格式准确率上优于基线模型

### Requirement: 提示词工程优化
多模态模型 SHALL 更可靠地调用 `screenshot`、`ocr`、`mouse_click` 等工具。

#### Scenario: 工具调用准确
- **WHEN** 用户指令包含屏幕截图
- **THEN** 模型输出正确的工具调用格式并正确执行

### Requirement: WSL 远程推理部署
macOS GUI 客户端 SHALL 能通过仅对可信局域网开放的 WSL 网关调用 vLLM，且不要求 macOS
本地存在对应模型权重或配置 API Key。网关 SHALL 保持 vLLM 后端仅监听 WSL 回环地址。

#### Scenario: macOS 调用 WSL LoRA 模型
- **WHEN** 配置 `MAX_PROVIDER=remote`、远程 `MAX_GUI_BASE_URL` 与
  `MODEL_NAME=qwen3.5-4b-lora`，且不设置 `MAX_PROVIDER_KEY`
- **THEN** 客户端向远程 OpenAI 兼容端点发送工具调用请求，且不执行本地权重检查
