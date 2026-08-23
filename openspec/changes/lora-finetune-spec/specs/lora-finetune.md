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
