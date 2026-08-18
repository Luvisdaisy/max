## Why

会话 `20260818-150248` 显示：视图像素换算是生效的，但 4B 在猜坐标。它给出超出视图高度的 `y`，工具默默夹到屏幕底边并在结果里写逻辑像素；下一轮又把逻辑坐标当视图像素再乘一次。模型无法一次看图像素点准，协议还在帮它把错点「变成成功」。

## What Changes

- 已有视图帧时，`mouse_move` / `mouse_click` / `mouse_drag` / `mouse_scroll` 的输入坐标 MUST 落在最近一帧 `[0, view_width) × [0, view_height)`。出界 MUST 返回中文错误（写明给出的坐标与视图宽高），MUST NOT 移动或点击，MUST NOT 把夹到屏幕边缘当成成功。
- 换算后仍可能因取整略超主屏：仅此种情况允许夹紧到屏幕内，并在结果中说明。
- 发给模型的动作摘要只报视图像素（及是否换算/夹紧），MUST NOT 写出逻辑坐标数字。后置截图 JSON 的 `cursor` 保持视图像素。`screen_info` 仍返回逻辑分辨率，供诊断，不用于点击。
- `target_id` 路径不变：仍用 `ocr_locate` 的逻辑中心，不按视图像素出界规则拒绝。
- GUI `system` 补一句：坐标必须在最近一帧视图宽高内；工具回写的也是视图像素，禁止把逻辑分辨率再当输入。
- 尚无截图时行为不变：输入仍当逻辑像素并夹紧到主屏。

不包含：截图网格、相对光标微调、图标级 spotting、用系统命令开应用、改 OCR。

## Capabilities

### New Capabilities

- （无）

### Modified Capabilities

- `desktop-gui-tools`：视图出界拒绝；动作摘要只含视图像素；屏幕夹紧仅用于换算后越出主屏。
- `react-agent`：GUI system 增加视图边界与「勿把逻辑坐标当输入」约定。

## Impact

- `src/max_gui/tools/desktop.py`：出界校验、摘要文案。
- `src/max_gui/agent/prompts.py`：系统契约。
- 测试：`tests/test_tools.py`、`tests/test_agent.py`（现有断言含逻辑坐标的用例需改）。
