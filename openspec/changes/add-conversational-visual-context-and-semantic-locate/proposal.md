## Why

当前 Agent 把每条用户输入都作为独立任务裁剪上下文。会话虽已保存截图，但后续“你看到了什么”之类的追问看不到上一轮观察；反过来，若直接复用旧 `ViewFrame` 或定位编号，又会带来陈旧坐标误操作风险。与此同时，`locate` 在真实 Dock 截图中返回大量同名 `icon`，无法告诉模型哪一个是 Chrome，导致模型只能猜编号或直接结束。

需要将“用于对话理解的历史观察”与“用于桌面执行的当前帧”严格分离，并为命名应用/控件提供可验证的语义定位，降低小模型在复杂 GUI 图上的猜测负担。

## What Changes

- 增加会话级只读视觉上下文，向连续对话提供有限的近期文本摘要和最近可读截图。
- 新用户回合开始桌面任务时，使旧 `ViewFrame`、定位命中与可执行事实失效；历史图只可用于回答或理解，不能驱动鼠标坐标、`target_id` 或点击。
- 调整推理上下文选择与单图优先级：本轮用户附件或当前任务新观察优先，缺少时才使用会话级历史观察。
- 新增语义定位能力：按目标名称和可选区域筛选视觉候选，只对不歧义的匹配项暴露可执行编号。
- 在 macOS 上增加只读 Dock 应用语义发现，优先通过辅助功能信息取得应用标题与边界；后续操作仍复用既有 `mouse_move` 与截图核验闭环。
- 为 OCR / icon caption 退化增加可诊断状态；无法可靠命名时明确返回未匹配，而不是把泛化 `icon` 伪装成目标。

## Capabilities

### New Capabilities

- `conversational-visual-context`: 规定会话级历史观察的有限保存、推理注入优先级，以及其不可执行边界。
- `semantic-ui-locate`: 规定按名称查询 UI 目标、macOS Dock 语义发现、视觉回退和不歧义编号输出。

### Modified Capabilities

- `session-store`: 持久化只读会话视觉上下文，并在新任务边界使可执行桌面状态失效。
- `multimodal-inference`: 将会话级历史观察纳入单图编码与上下文预算选择，同时保持用户附件和当前观察优先。
- `react-agent`: 在新回合建立任务上下文时区分只读历史观察与可执行当前帧，并向模型说明其安全边界。
- `desktop-gui-tools`: 允许语义定位结果安全地进入既有 `mouse_move(target_id=...)` 核验链路，不放宽坐标或点击门禁。
- `ui-locate-coordinate-safety`: 规定语义定位仅在当前活动帧上产生可执行编号，历史图查询只供观察。

## Impact

主要影响 `src/max_gui/agent/context.py`、`graph.py`、`src/max_gui/session/store.py`、`src/max_gui/inference/client.py`、`src/max_gui/tools/locate.py`、OmniParser worker、桌面工具与对应测试。macOS Dock 语义发现可能需要调用系统辅助功能 API；若权限或元素支持不足，必须安全降级到视觉定位，不引入对外服务或长期数据库。
