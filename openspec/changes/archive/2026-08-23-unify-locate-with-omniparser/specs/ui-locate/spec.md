## ADDED Requirements

### Requirement: 全屏界面定位工具

系统 MUST 提供名为 `locate` 的只读工具。该工具 MUST 对一张已有截图做可交互控件检测，在视图尺寸副本上绘制编号边界框，返回 JSON（每项含 `id`、`label`、可选 `role`、视图像素与逻辑像素的框和中心）以及该带框图，并把编号到逻辑中心写入当前会话的定位表。MUST NOT 要求用户确认。MUST NOT 接受用于过滤的 `query`。MUST NOT 点击或移动指针。框表示可点热区，MUST NOT 声称只覆盖文字行。

`path` 可省略：省略时 MUST 使用当前会话视图帧的 `image_path`。当前无视图帧或该文件不存在时 MUST 返回中文错误，且 MUST NOT 启动检测进程。显式 `path` MUST 解析为绝对路径，且 MUST 位于已配置的截图目录或工作区根之内；越权 MUST 拒绝且不读取、不调用检测。

#### Scenario: 定位成功回注带框图

- **WHEN** 模型调用 `locate`，`path` 指向一张已存在的截图，且检测返回至少一个框
- **THEN** 工具返回含编号项的 JSON，附带画了对应编号框的图像，且 `coordinate_space` 为 `view`

#### Scenario: 省略路径使用当前截图

- **WHEN** 当前会话已有视图帧且该 PNG 存在，模型调用 `locate` 且未传 `path`
- **THEN** 工具对该帧图像做检测，不要求再抄路径

#### Scenario: 无截图且未给路径

- **WHEN** 当前会话尚无视图帧，模型调用 `locate` 且未传 `path`
- **THEN** 工具返回中文错误，且不启动检测进程

#### Scenario: 拒绝任意系统路径

- **WHEN** 模型调用 `locate`，`path` 指向截图目录与工作区之外
- **THEN** 工具返回权限错误，且不读取该文件、不调用检测

### Requirement: 最多保留四十个编号框

写入 JSON、叠加图与命中表的框 MUST 不超过 40 个。超出时 MUST 先做重叠合并，再丢弃过小框，再按检测分数（无分数则按面积）保留较大者，然后按从上到下、从左到右编号。被截断的框 MUST NOT 出现在 JSON、叠加图或命中表中。

#### Scenario: 超过四十个框则截断

- **WHEN** 检测器返回 50 个互不重叠的框
- **THEN** 工具结果至多含 `id` 1 到 40，且叠加图上没有第 41 号

#### Scenario: 零框视为失败

- **WHEN** 检测器成功返回但框列表为空
- **THEN** 工具返回可跳过的中文错误，且不附带伪造的边界框图

### Requirement: 首次调用再启动独立 OmniParser 服务

系统 MUST NOT 在 `max-gui` 或 `max-gui serve` 启动时默认拉起 OmniParser。第一次合法的 `locate` 调用 MUST 再启动独立于主 Qwen 服务与 OCR 服务的检测进程（不同端口，不启用 Qwen tool parser）。同一进程后续 `locate` 调用 MUST 复用已就绪的服务。并发的首次调用 MUST 只启动一个检测进程。项目运行时环境 MUST NOT 因此新增 torch 或 ultralytics。

#### Scenario: 冷启动后复用

- **WHEN** 当前没有可用的定位服务，模型第一次成功进入检测的 `locate` 调用完成，随后再次调用 `locate`
- **THEN** 第二次不启动第二个检测进程

#### Scenario: 主 serve 不拉起定位

- **WHEN** 用户只运行 `max-gui serve` 加载 Qwen
- **THEN** 系统不启动 OmniParser 进程

### Requirement: caption 失败仍可出框

YOLO 检测成功而图标描述模型失败时，`locate` MUST 仍返回编号框；缺描述的项 MUST 使用 OCR 文本或简短类别作为 `label`。MUST NOT 因 caption 失败而丢弃已检出的框。

#### Scenario: 无 caption 仍定位

- **WHEN** 检测返回框但 caption 不可用
- **THEN** 工具仍回注带框图与 JSON，项含 `id` 与非空 `label`

### Requirement: 定位失败则跳过

当检测进程启动失败、连接失败、推理失败或超时，`locate` MUST 返回说明界面定位不可用、可继续根据已有截图作答的中文错误，且 MUST 附带简短失败原因或日志路径。MUST NOT 把异常抛出 ReAct 图外，MUST NOT 结束用户回合。worker 标准输出与错误 MUST 写入项目 `artifacts/logs/` 下的定位日志，MUST NOT 丢弃到空设备以致无法排查。

#### Scenario: 失败后图继续

- **WHEN** 模型调用 `locate` 且 OmniParser 进程不可用
- **THEN** `observe` 收到可跳过的中文错误，图回到 `think`

#### Scenario: 跳过文案含原因

- **WHEN** worker 启动后立即退出
- **THEN** 工具结果含「界面定位不可用」，并含退出码、日志摘录或日志路径之一
