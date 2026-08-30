## Context

默认注册表目前同时装配截图、OCR、OmniParser `locate` 和桌面动作。`locate` 的结果会写入当前截图对应的 `locate_hits`，随后由 `mouse_move(target_id)` 换算为桌面逻辑坐标。该链路涉及独立进程、检测标签质量和坐标事实生命周期；当检测不到语义目标时，模型容易在同一截图上重复定位，阻塞评测任务。

本次只改变默认 Agent 的可见能力，不删除 OmniParser 实现与持久化字段。这样可以立即停止不稳定调用，同时保留后续重新启用或离线调试所需的代码。

## Goals / Non-Goals

**Goals:**

- 从默认 `ToolRegistry` 和发送给模型的 schema 中移除 `locate`。
- 让系统提示词明确采用“先截图、再用当前截图视图像素移动”的操作协议。
- 保持截图后的坐标帧、鼠标移动后置截图、点击门禁和 OCR 能力不变。
- 用自动化测试锁定工具集合与提示词契约，避免 `locate` 被意外重新暴露。

**Non-Goals:**

- 不删除 `src/max_gui/tools/locate.py`、OmniParser worker、相关配置或历史会话字段。
- 不重写坐标换算、PyAutoGUI 后端或 Mind2Web 评测报告逻辑。
- 不保证模型仅凭截图一定能准确点击；本次只移除定位器依赖。

## Decisions

1. **在默认装配层禁用，而非删除实现。**
   `build_default_registry` 不再把 `locate_tool` 加入工具列表；保留可选参数和底层模块，降低对测试注入、旧会话和后续实验的破坏。相比删除整个模块，这能把变更限制在 Agent 可见边界。

2. **以提示词约束配合 schema 移除。**
   `compose_gui_system_prompt` 删除 `locate`、`target_id` 和“定位编号”路径，强调 `screenshot` 后使用视图像素。注册表未注册 `locate` 时，模型即使自行生成旧名称也只能得到结构化 `unknown_tool` 错误。

3. **保留内部 target_id 兼容分支。**
   `mouse_move` 的旧 `target_id` 解析和会话定位表暂不删除；它们不再由默认 schema 产生，且不会启动 OmniParser。这样旧会话恢复不会因字段缺失崩溃，也避免将本次禁用扩大成坐标协议重构。

4. **用契约测试而非真实桌面测试验证禁用。**
   测试检查默认注册表名称、导出的 schema、提示词文本和未知工具返回码；真实鼠标操作继续使用现有假后端测试。

## Risks / Trade-offs

- [Risk] 模型仍可能输出旧的 `locate` 工具调用。→ 注册表返回 `unknown_tool`，提示词同时明确禁止该路径；评测日志可统计残留调用。
- [Risk] 没有检测框时直接使用坐标可能增加误点。→ 保留“截图后移动、红十字核验、再点击”的既有门禁，并要求动作后继续截图。
- [Risk] 旧会话中的 `locate_hits` 仍可能存在。→ 新回合开始时沿用现有桌面上下文清理；旧 `target_id` 只有在内部路径仍满足当前帧约束时才可解析。

## Migration Plan

1. 更新 OpenSpec delta、默认注册表和提示词。
2. 更新注册表/schema/提示词测试并运行 Ruff 与完整 pytest。
3. Mind2Web 评测重新运行时确认工具 schema 不含 `locate`，并观察模型是否改用 `mouse_move(x, y)`。
4. 若未来恢复定位器，只需重新装配 `locate_tool` 并恢复提示词/规格；无需迁移会话文件。

## Open Questions

暂无。是否彻底删除 OmniParser 与 `target_id` 属于后续独立清理变更，不在本次范围内。
