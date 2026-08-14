# ocr-tool Specification

## Purpose

整图 OCR 与文字定位：在主 VL 模型看不清屏幕文字或需要可点坐标时，用独立 PaddleOCR-VL-1.5 识别已有图像。

## Requirements

### Requirement: 整图 OCR 工具

系统 MUST 提供名为 `ocr` 的工具。该工具 MUST 接受图像 `path`，对整张图做文字识别，并返回纯文本结果。`ocr` MUST 使用任务提示 `OCR:`。`ocr` MUST NOT 使用 spotting，MUST NOT 暴露表格、公式、图表或印章任务。MUST NOT 要求用户确认。

#### Scenario: 识别截图文字

- **WHEN** 模型调用 `ocr`，`path` 指向一张已存在的截图，且 OCR 推理成功
- **THEN** 工具返回该图的识别文本，且结果不含图像引用

#### Scenario: 缺路径或文件不存在

- **WHEN** 模型调用 `ocr` 但未提供 `path`，或文件不存在
- **THEN** 工具返回中文错误，且不启动新的推理进程

### Requirement: 文字定位与边界框

系统 MUST 提供名为 `ocr_locate` 的工具。该工具 MUST 接受图像 `path`，使用任务提示 `Spotting:` 识别文字行位置，在视图尺寸的副本上绘制编号边界框，并返回 JSON（每项含 `id`、`text`、视图像素与逻辑像素的框和中心）以及该带框图。MUST NOT 要求用户确认。MUST NOT 暴露表格、公式、图表或印章任务。框表示文字行，MUST NOT 声称覆盖无文字的图标控件。

#### Scenario: 定位截图文字

- **WHEN** 模型调用 `ocr_locate`，`path` 指向一张已存在的截图，且 spotting 推理与解析成功
- **THEN** 工具返回含编号项的 JSON，并附带画了对应编号框的图像

#### Scenario: 无法解析定位结果

- **WHEN** 模型调用 `ocr_locate` 且推理返回了文本，但无法解析出任何框
- **THEN** 工具返回中文错误，且不附带伪造的边界框图

#### Scenario: 缺路径或文件不存在

- **WHEN** 模型调用 `ocr_locate` 但未提供 `path`，或文件不存在
- **THEN** 工具返回中文错误，且不启动新的推理进程

### Requirement: 图像路径限定在截图目录与工作区

`ocr` 与 `ocr_locate` MUST 将 `path` 解析为绝对路径，且该路径 MUST 位于已配置的截图目录或工作区根之内。逃出这两个根的路径 MUST 被拒绝。MUST NOT 使用仅允许工作区的路径解析器作为唯一入口。

#### Scenario: 允许读取截图目录

- **WHEN** 模型调用 `ocr`，`path` 为截图目录内的 PNG
- **THEN** 工具读取该文件并尝试识别

#### Scenario: 允许读取工作区图像

- **WHEN** 模型调用 `ocr`，`path` 为工作区内的图像文件
- **THEN** 工具读取该文件并尝试识别

#### Scenario: 拒绝任意系统路径

- **WHEN** 模型调用 `ocr_locate`，`path` 指向截图目录与工作区之外
- **THEN** 工具返回权限错误，且不读取该文件、不调用推理

### Requirement: 首次调用再启动独立 OCR 服务

系统 MUST NOT 在 `max-gui` 或 `max-gui serve` 启动时默认拉起 OCR 模型。第一次合法的 `ocr` 或 `ocr_locate` 调用 MUST 再启动独立于主 Qwen 服务的 vLLM 进程（不同端口、不启用 Qwen tool parser）。同一进程后续 `ocr` 与 `ocr_locate` 调用 MUST 复用已就绪的服务。并发的首次调用 MUST 只启动一个 OCR 进程。

#### Scenario: 冷启动后复用

- **WHEN** 当前没有可用的 OCR 服务，模型第一次成功进入推理的 `ocr` 调用完成，随后调用 `ocr_locate`
- **THEN** `ocr_locate` 不启动第二个 OCR vLLM 进程

#### Scenario: 主 serve 不拉起 OCR

- **WHEN** 用户只运行 `max-gui serve` 加载 Qwen
- **THEN** 系统不启动 PaddleOCR-VL 进程

### Requirement: vLLM 失败后阻塞回退 transformers

OCR 推理 MUST 先走已就绪或刚启动的 vLLM OpenAI 兼容接口。启动失败、连接失败或推理失败时，工具 MUST 阻塞地改用独立推理环境中的 transformers 加载本地 `model/paddleocr-vl-1.5`。`ocr` MUST 使用提示 `OCR:`；`ocr_locate` MUST 使用提示 `Spotting:`。项目运行时环境 MUST NOT 因此新增 PaddlePaddle 或把 OCR 权重加载进 TUI 主进程。

#### Scenario: vLLM 成功则不回退

- **WHEN** OCR vLLM 返回识别文本
- **THEN** 工具直接返回该文本，且不启动 transformers 回退

#### Scenario: vLLM 失败后 transformers 成功

- **WHEN** `ocr_locate` 的 OCR vLLM 不可用，但 transformers 回退识别成功
- **THEN** 工具使用 `Spotting:` 回退结果继续解析，且本轮在回退完成前不返回

### Requirement: 两档都失败则跳过

当 vLLM 与 transformers 均失败或超时，`ocr` MUST 返回说明 OCR 不可用、可继续根据已有截图作答的中文错误。MUST NOT 把异常抛出 ReAct 图外，MUST NOT 结束用户回合。

#### Scenario: 全部失败后图继续

- **WHEN** 模型调用 `ocr`，vLLM 与 transformers 都失败
- **THEN** `observe` 收到可跳过的中文错误，图回到 `think`

### Requirement: 定位失败则跳过

当 vLLM 与 transformers 均失败或超时，或 spotting 结果无法解析，`ocr_locate` MUST 返回说明定位不可用、可继续根据已有截图作答的中文错误。MUST NOT 把异常抛出 ReAct 图外，MUST NOT 结束用户回合。

#### Scenario: 全部失败后图继续

- **WHEN** 模型调用 `ocr_locate`，vLLM 与 transformers 都失败
- **THEN** `observe` 收到可跳过的中文错误，图回到 `think`
