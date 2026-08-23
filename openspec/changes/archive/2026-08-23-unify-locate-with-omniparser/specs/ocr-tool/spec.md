## MODIFIED Requirements

### Requirement: 整图 OCR 工具

系统 MUST 提供名为 `ocr` 的工具。该工具 MUST 接受图像 `path`，对整张图做文字识别，并返回纯文本结果。`ocr` MUST 使用任务提示 `OCR:`。`ocr` MUST NOT 使用 spotting，MUST NOT 暴露表格、公式、图表或印章任务，MUST NOT 画编号框。MUST NOT 要求用户确认。可点控件定位 MUST 由 `locate` 提供，MUST NOT 再通过本工具出框。

#### Scenario: 识别截图文字

- **WHEN** 模型调用 `ocr`，`path` 指向一张已存在的截图，且 OCR 推理成功
- **THEN** 工具返回该图的识别文本，且结果不含图像引用

#### Scenario: 缺路径或文件不存在

- **WHEN** 模型调用 `ocr` 但未提供 `path`，或文件不存在
- **THEN** 工具返回中文错误，且不启动新的推理进程

### Requirement: 图像路径限定在截图目录与工作区

`ocr` MUST 将 `path` 解析为绝对路径，且该路径 MUST 位于已配置的截图目录或工作区根之内。逃出这两个根的路径 MUST 被拒绝。MUST NOT 使用仅允许工作区的路径解析器作为唯一入口。

#### Scenario: 允许读取截图目录

- **WHEN** 模型调用 `ocr`，`path` 为截图目录内的 PNG
- **THEN** 工具读取该文件并尝试识别

#### Scenario: 允许读取工作区图像

- **WHEN** 模型调用 `ocr`，`path` 为工作区内的图像文件
- **THEN** 工具读取该文件并尝试识别

#### Scenario: 拒绝任意系统路径

- **WHEN** 模型调用 `ocr`，`path` 指向截图目录与工作区之外
- **THEN** 工具返回权限错误，且不读取该文件、不调用推理

### Requirement: 首次调用再启动独立 OCR 服务

系统 MUST NOT 在 `max-gui` 或 `max-gui serve` 启动时默认拉起 OCR 模型。第一次合法的 `ocr` 调用 MUST 再启动独立于主 Qwen 服务的 vLLM 进程（不同端口、不启用 Qwen tool parser）。同一进程后续 `ocr` 调用 MUST 复用已就绪的服务。并发的首次调用 MUST 只启动一个 OCR 进程。MUST NOT 因 `locate` 而启动 OCR 进程。

#### Scenario: 冷启动后复用

- **WHEN** 当前没有可用的 OCR 服务，模型第一次成功进入推理的 `ocr` 调用完成，随后再次调用 `ocr`
- **THEN** 第二次不启动第二个 OCR vLLM 进程

#### Scenario: 主 serve 不拉起 OCR

- **WHEN** 用户只运行 `max-gui serve` 加载 Qwen
- **THEN** 系统不启动 PaddleOCR-VL 进程

### Requirement: vLLM 失败后阻塞回退 transformers

OCR 推理 MUST 先走已就绪或刚启动的 vLLM OpenAI 兼容接口。启动失败、连接失败或推理失败时，工具 MUST 阻塞地改用独立推理环境中的 transformers 加载本地 `model/paddleocr-vl-1.5`。`ocr` MUST 使用提示 `OCR:`。项目运行时环境 MUST NOT 因此新增 PaddlePaddle 或把 OCR 权重加载进 TUI 主进程。

#### Scenario: vLLM 成功则不回退

- **WHEN** OCR vLLM 返回识别文本
- **THEN** 工具直接返回该文本，且不启动 transformers 回退

#### Scenario: vLLM 失败后 transformers 成功

- **WHEN** `ocr` 的 OCR vLLM 不可用，但 transformers 回退识别成功
- **THEN** 工具使用 `OCR:` 回退结果返回文本，且本轮在回退完成前不返回

## REMOVED Requirements

### Requirement: 文字定位与边界框

**Reason**：可点编号改由 OmniParser `locate` 提供，避免文字行框与控件框抢同一套 `target_id`。

**Migration**：点控件改调 `locate` 再 `mouse_move(target_id)`；需要抄字时调 `ocr`。

### Requirement: 定位失败则跳过

**Reason**：该失败路径随 `ocr_locate` 一起移除，由 `ui-locate` 的定位失败跳过承接。

**Migration**：见 `locate` 工具的失败文案。
