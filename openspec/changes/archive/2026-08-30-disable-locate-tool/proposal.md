## Why

当前 `locate` 依赖独立的 OmniParser 检测进程，并且要求模型先理解检测标签再复用 `target_id`。在 Online-Mind2Web 实测中，语义查询容易返回空候选，模型会重复调用定位工具而无法进入实际的鼠标操作。现阶段需要先关闭这条不稳定路径，回到“截图 + 视图像素坐标 + OCR 辅助读字”的可控评测路径。

## What Changes

- **BREAKING**：默认 Agent 工具注册表不再暴露 `locate`，模型请求的工具 schema 中不再包含该工具。
- 将 GUI 系统提示词改为仅指导模型使用最新截图中的视图像素坐标进行 `mouse_move`，需要读字时使用 `ocr`。
- 更新 OCR 工具提示，删除“用 locate 定位控件”的建议，改为坐标定位说明。
- 保留 OmniParser 与历史定位状态代码作为暂不启用的兼容实现，不在默认运行链路中启动或调用。
- 增加注册表、工具 schema 与提示词回归测试，确保模型不能通过默认工具集合调用 `locate`。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `agent-tools`：默认工具集合移除 `locate`，调用该名称按未知工具处理。
- `react-agent`：GUI 系统契约不再要求或推荐 `locate` / `target_id`，改用截图视图像素与 OCR。

## Impact

- 影响 `build_default_registry`、GUI 系统提示词、OCR 工具说明、相关 Agent/工具测试与评测提示。
- 默认运行不再懒启动 OmniParser；OmniParser 代码、配置和会话旧字段仍保留，避免扩大迁移范围。
- 依赖 `target_id` 的旧模型调用会收到参数校验或工具错误，需要改为使用最新截图上的视图像素坐标。
