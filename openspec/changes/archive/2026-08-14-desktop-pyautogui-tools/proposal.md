## Why

第一版 Agent 只能操作工作区文件，看不见也点不到桌面。要做成 GUI Agent，必须在现有 ReAct 工具协议上补截图回注和键鼠执行；否则 2B VL 模型无法根据画面给坐标。调研已收敛到 PyAutoGUI 最小工具面，现在把它写成可落地的变更。

## What Changes

- 新增 7 个桌面工具：`screenshot`、`screen_info`、`mouse_move`、`mouse_click`、`mouse_drag`、`keyboard_type`、`keyboard_press`
- 补齐工具结果的多模态回注：`screenshot` 必须把图像编进下一轮 `think` 的 Chat Completions，不能只回文件路径文本
- 桌面动作使用逻辑像素坐标，并在截图 / 屏幕信息中返回 Retina `scale`
- 加严确认门：点击、拖拽、打字、按键必须确认；会话 `auto_approve` 默认不覆盖桌面工具
- macOS 屏幕录制 / 辅助功能失败时返回可照做的中文步骤
- 禁止经 `run_python` 导入 `pyautogui` 等桌面控制库绕过工具层
- 测试使用假后端，CI 不真实移动鼠标或截屏

## Capabilities

### New Capabilities

- `desktop-gui-tools`：基于 PyAutoGUI 的桌面感知与执行（截图、屏幕信息、移鼠、点按、拖拽、输入文本、按键），含逻辑坐标、权限错误与安全约束

### Modified Capabilities

- `agent-tools`：默认注册桌面工具；破坏性桌面工具的确认策略与工作区工具分离；`run_python` 禁止导入桌面控制库
- `multimodal-inference`：`to_chat_messages` 必须把 tool 消息中的图像引用编成 `image_url` 部件
- `session-store`：会话增加独立的桌面自动批准开关，与现有 `auto_approve` 分开
- `tui-repl`：桌面工具确认不受普通 `auto_approve` 影响；权限失败文案对用户可见

## Impact

- 包：`src/max_gui/tools/` 新增桌面工具模块；`tools/protocol.py` / `registry.py` 需支持带图像引用的工具结果
- 推理：`src/max_gui/inference/client.py` 的 `to_chat_messages` 扩展 tool / assistant 图像编码
- 会话：`Session` 增加 `auto_approve_desktop`（或等价字段）
- TUI：确认门按工具类别判断；展示桌面权限错误
- 依赖：新增 `pyautogui`（及 `pyscreeze`）；中文粘贴需要时再加 `pyperclip`
- 本地数据：截图写入 `artifacts/screenshots/`，不进 git
- 目标运行时仍是 macOS Apple Silicon；Windows / Linux 不作为本变更一等支持
