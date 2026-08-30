# ui-locate-coordinate-safety Specification

## Purpose

约束 OmniParser `locate` 的检测编号、桌面坐标帧与带框图回注尺寸，避免高 DPI 与历史图片导致错误桌面输入。
## Requirements
### Requirement: 定位编号必须绑定当前截图坐标帧

系统 MUST 仅在 `locate` 的源图绝对路径等于当前会话 `ViewFrame.image_path` 时，把检测编号映射到逻辑桌面中心并写入可供 `mouse_move`、`mouse_scroll` 使用的定位表。显式 `path` 指向历史截图、工作区图片或带框副本时，系统 MUST 仍可返回检测框与带框图，但该结果 MUST 标为仅观察，MUST NOT 写入可执行定位表，并 MUST 清空之前的定位表。路径、图像尺寸或图像内容相同均 MUST NOT 作为坐标帧相同的依据。

#### Scenario: 当前截图的编号可移动指针

- **WHEN** 模型先成功调用 `screenshot`，再以省略 `path` 的方式调用 `locate`
- **THEN** `locate` 返回视图与逻辑坐标，并将编号的逻辑中心写入当前会话定位表

#### Scenario: 历史 Retina 截图仅供观察

- **WHEN** 当前视图帧为另一张图，模型调用 `locate` 且 `path` 指向一张 2 倍物理像素的历史截图
- **THEN** 工具返回带框图与图像坐标，清空定位表，且后续使用该编号调用 `mouse_move` MUST 返回中文错误而不移动指针

### Requirement: 带框图与视图坐标使用同一最终尺寸

系统 MUST 在返回 `locate` 结果前确定模型实际接收的带框图像素尺寸。JSON 中 `coordinate_space=view` 的框、中心与叠加图 MUST 使用该同一尺寸。若图像字节上限导致图像需要缩小，系统 MUST 在缩小后的尺寸上重新投影并绘制编号，或返回可跳过的中文错误；MUST NOT 返回与模型看到的图尺寸不一致的视图坐标。

#### Scenario: 带框图触发字节限制

- **WHEN** 定位叠加图在当前视图尺寸下超过配置的图像字节上限
- **THEN** 模型收到的叠加图尺寸与 JSON `view` 框的坐标空间一致，且 `target_id` 的逻辑中心仍对应该框中心

### Requirement: 语义定位仍受当前帧坐标边界约束

语义视觉定位和 macOS Dock 语义发现 MUST 仅在其候选边界可投影到当前活动 `ViewFrame` 时生成可执行编号。历史图、屏幕外元素、投影失败或观察专用图 MUST 标为仅观察并清空可执行定位表。

#### Scenario: 历史观察查询 Chrome 仅供描述
- **WHEN** 模型对会话级历史截图执行 Chrome 查询而该图不是当前活动帧
- **THEN** 返回结果仅供观察，不产生可供 `mouse_move` 使用的编号
