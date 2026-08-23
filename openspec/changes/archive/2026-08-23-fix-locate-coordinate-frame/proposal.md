## Why

`locate` 目前允许对历史截图或工作区图片建立可用于桌面操作的 `target_id`。当该图片不是当前视图帧时，系统会把物理图像像素当作逻辑桌面像素；在 Retina 或其他高 DPI 环境中会把光标移到错误位置。带框图在回注前还会再次进行图像预处理，极端情况下也可能使模型看到的图尺寸与 JSON 中的视图坐标不一致。

## What Changes

- 将可执行的 `target_id` 限定为当前会话、当前截图视图帧生成的定位结果；历史截图、工作区图片与带框副本仍可检测和展示，但不得写入可供桌面移动、滚动或点击使用的命中表。
- 为定位结果显式保留其坐标帧来源，并在坐标帧已失效或不匹配时返回中文可恢复错误，不执行桌面移动。
- 确保回注给模型的带框图与结果 JSON 使用同一视图尺寸；图像因字节限制需要再次缩小时，同步更新框图与模型可见坐标，或拒绝生成不一致结果。
- 为 OmniParser HTTP worker 限制本地路径协议：非本机地址不得接收仅在主进程可见的绝对图片路径。

## Capabilities

### New Capabilities

- `ui-locate-coordinate-safety`：定义 OmniParser 定位结果的坐标帧归属、可执行编号边界与带框图回注一致性。

### Modified Capabilities

- `desktop-gui-tools`：鼠标工具对 `target_id` 的使用改为只接受与当前桌面视图一致的定位命中。
- `runtime-config`：OmniParser 本地 worker 地址的配置约束发生变化。

## Impact

- 代码：`src/max_gui/tools/locate.py`、`overlay.py`、`desktop.py`、`inference/client.py`、`inference/omniparser.py` 与相关测试。
- 行为：模型不能再把任意历史或工作区图片的检测编号直接用于桌面输入；需要先对当前截图重新调用 `locate`。
- 不新增模型、网络依赖或运行时进程。
