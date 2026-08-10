## 1. 工具契约与注册入口

- [x] 1.1 在 `src/max_agent/tools/` 建立最小工具 Protocol、Pydantic 输入/输出模型、标准失败码和不泄露图像内容的回执。
- [x] 1.2 实现 `tools/registry.py`，支持按名称注册、发现和调用工具，并将未知名称、输入校验和运行时异常转换为失败回执。
- [x] 1.3 为工具契约和注册表补充单元测试，覆盖成功调用、未知工具、无效输入和异常边界。

## 2. 屏幕与文字观察

- [x] 2.1 实现 `perception/screen.py` 的 `observe_screen`，返回内存图像、物理像素尺寸、显示器边界和 DPI 元数据，并支持显示器选择。
- [x] 2.2 实现 `perception/ocr.py` 的 `recognize_text`，将本地 PaddleOCR 结果转换为文本、置信度和像素边界框；禁止资源下载并将初始化错误转换为回执。
- [x] 2.3 为截图和 OCR 提供假后端/合成图像测试，验证无文件写入、无桌面输入、无效显示器和 OCR 资源不可用的行为。

## 3. UI 与视觉增强工具

- [x] 3.1 实现 `perception/uia.py` 的只读窗口元素观察，限制遍历数量并返回元素名称、角色、边界和可用状态。
- [x] 3.2 实现 `perception/vision.py` 的图像预处理和模板匹配，使用调用方提供的内存图像并返回像素坐标结果。
- [x] 3.3 实现 `perception/som.py` 的按需内存 Set-of-Mark 标注，并返回标记与边界的对应关系。
- [x] 3.4 为 UIA、视觉和 SoM 增加单元测试，覆盖可访问目标、不可访问目标、匹配结果和无磁盘写入边界。

## 4. 集成、文档与验证

- [x] 4.1 在默认注册表中注册全部感知工具，并验证所有工具均通过该入口调用。
- [x] 4.2 更新 `tech-design.md` 的当前实现基线、模块职责和验证说明，明确工具仍为只读且不包含编排或桌面执行，并记录恢复后的 Doctor CLI。
- [x] 4.3 运行 `python -m unittest discover -s tests -v`、`python -m pip check` 与 `max-agent doctor --artifact-root artifacts`，记录受限/非交互会话下的观察工具限制。
- [x] 4.4 在授权的交互式 Windows 会话中人工验证内存截图、只读 UIA 观察和本地 OCR；不得对真实业务窗口执行输入。

## 5. 恢复 Doctor CLI

- [x] 5.1 恢复 `max-agent doctor` 的参数解析，支持 `--artifact-root` 与显式 `--desktop-probe`，并复用现有 Doctor 操作函数。
- [x] 5.2 为默认无输入 Doctor、显式桌面探针参数和无效参数补充 CLI 单元测试。
- [x] 5.3 将桌面探针的 Tk 夹具替换为进程内 Win32 原生窗口、`Edit` 与自动复选 `Button` 控件；检查 `SendInput` 返回值、原生文本读取、按钮选中状态、前台安全门和子进程异常边界，并在交互式 Windows 会话中复验。
