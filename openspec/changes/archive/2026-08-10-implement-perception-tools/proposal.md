## Why

技术设计已定义 GUI Agent 所需的感知工具边界，但仓库目前只有用于 Doctor 的独立依赖探测，尚未提供可由未来编排器注册和调用的截图、OCR、UI Automation、视觉处理与 Set-of-Mark 工具。实现这些无副作用的观察能力，才能让后续规划、审批和执行模块消费一致、可测试的屏幕状态。

## What Changes

- 新增 `tools` 的工具契约与注册表，并将所有感知实现置于 `src/max_agent/tools/perception/`。
- 提供 `observe_screen`：使用 `mss` 获取内存中的屏幕或指定显示器截图，并附带物理像素、显示器和 DPI 元数据。
- 提供 `recognize_text`：通过 PaddleOCR 识别调用方提供的图像，返回带置信度和边界框的结构化文本；不会下载模型、读取屏幕或写出图像。
- 提供可选的 UI Automation 观察、OpenCV 图像预处理与模板匹配，以及按需生成 Set-of-Mark 标注图的工具。
- 为所有工具提供确定性的输入/输出契约、失败回执和单元测试；工具只观察和处理内存数据，不执行桌面输入，也不保存截图。
- 恢复独立的 `max-agent doctor` 命令与 `--artifact-root` 参数；`--desktop-probe` 保持显式 opt-in，使用进程内 Win32 原生顶层窗口、`Edit` 与 `Button` 控件验证键盘和鼠标输入，并继续以前台句柄确认作为唯一输入放行条件。
- 更新技术设计报告，将这些感知模块标记为当前已实现基线，并保留编排、模型、审批和桌面执行为后续能力。

## Capabilities

### New Capabilities

- `perception-tools`: 面向受控 Windows 桌面会话的只读屏幕、文本、UI 元素与视觉标注观察工具，以及统一的工具注册入口。

### Modified Capabilities

- `runtime-bootstrap`: 恢复公开 Doctor CLI 入口，并明确默认无输入诊断与显式桌面探针的参数语义。

## Impact

- 新增 `src/max_agent/tools/base.py`、`src/max_agent/tools/registry.py` 与 `src/max_agent/tools/perception/` 下的实现。
- 新增感知工具的单元测试，并更新 `tech-design.md` 的当前实现边界和验证说明。
- 复用现有 `mss`、PaddleOCR、OpenCV 和 `pywinauto` 依赖；桌面探针仅通过 Python 标准库 `ctypes` 调用 Win32 API，不依赖 Tk 或外部业务应用；恢复 Doctor CLI，但不新增模型下载或通用桌面控制能力。
