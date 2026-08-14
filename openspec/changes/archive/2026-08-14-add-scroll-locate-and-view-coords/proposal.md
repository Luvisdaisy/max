## Why

第二周桌面模块还缺滚轮，以及「文字/UI 区域框 + 可点坐标」。同时线上已能复现：模型按自己看见的截图点像素，工具却按逻辑像素执行，Retina 缩放和 `prepare_image` 缩边叠在一起，指针会系统性地打偏。这三条不一起改，画框也接不进点击。

## What Changes

- 新增桌面工具 `mouse_scroll`：在当前指针或指定点滚动，走桌面确认门。
- 新增只读工具 `ocr_locate`：对已有图像做 PaddleOCR-VL `Spotting:`，解析文字行框，画出编号边界框，并返回可点中心坐标。现有 `ocr` 仍只做整图纯文本。
- **BREAKING（对模型）**：`mouse_move` / `mouse_click` / `mouse_drag` / `mouse_scroll` 的输入坐标改为「模型实际看到的那张图」上的像素（视图像素），由工具换算成逻辑像素再交给 PyAutoGUI。不再要求模型自己换算 Retina `scale`。
- `screenshot` 摘要补充视图像素宽高、逻辑宽高、原点偏移（全屏或 region），便于换算与核对。
- 不改跨平台键位/权限文案，不写单独的《单元测试报告》。仓库内仍补行为测试。

## Capabilities

### New Capabilities

- （无。滚轮与视图像素落在现有桌面规格；定位框落在现有 OCR 规格。）

### Modified Capabilities

- `desktop-gui-tools`：增加滚轮；桌面坐标契约从「模型给逻辑像素」改为「模型给视图像素，工具换算」；截图摘要携带视图尺寸。
- `ocr-tool`：在禁止表格/公式/图表/印章的前提下，允许 `Spotting:` 任务，并新增 `ocr_locate` 工具。
- `agent-tools`：默认注册表增加 `mouse_scroll`、`ocr_locate`；`mouse_scroll` 走桌面确认门，`ocr_locate` 不确认。
- `multimodal-inference`：图像预处理必须报告编码后的实际宽高，供桌面坐标换算与截图摘要使用。

## Impact

- 代码：`desktop/backend.py`、`desktop/fake.py`、`desktop/pyautogui_backend.py`、`tools/desktop.py`、`tools/ocr.py`、`inference/ocr.py`、`inference/ocr_transformers_worker.py`、`inference/images.py`、`tools/registry.py`、相关测试。
- 行为：模型点鼠标时按「看见的图」给坐标；需要精确点文字时先 `ocr_locate` 再用返回的中心点或编号。
- 依赖：不新增项目 `.venv` 包；spotting 复用已有 PaddleOCR-VL 运行时。
- 范围外：Windows/Linux 一等支持、真控件检测（OmniParser / 辅助功能树）、横向滚动、每次截图自动 OCR。
