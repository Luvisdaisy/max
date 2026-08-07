# 第一周周报

## 本周目标

完成 Windows 开发环境与基础工具的可复核验证，为第二周桌面感知和受控控制模块建立安全前置条件。

## 完成情况

- 完成 GUI 智能体技术调研与系统架构设计，详见 `research-report.md` 和 `architecture-report.md`。
- 在 Conda `max` 环境中核验 Python 3.12、CUDA、GPU、BF16 和依赖一致性。
- 新增 Doctor：默认以无输入方式检查 mss、PyAutoGUI、OpenCV、PaddleOCR 与 pynput，并以通过、失败、跳过分组输出结果。
- 增加显式受控桌面探针；只有指定 `--desktop-probe` 才会在临时窗口内执行点击和输入验证。

## 验证结果

使用以下命令执行环境核验：

```powershell
conda run -n max python -m max_agent.cli doctor --artifact-root artifacts
```

自动化测试覆盖命令重命名、聊天命令分发、结果摘要、基础工具探测和显式探针开关。运行记录存于 Git 忽略的 `artifacts/`，不包含模型信息、真实截图、个人数据或密钥。

## 问题与分析

- 非交互式会话可能无法取得桌面截图或窗口焦点；Doctor 会把相应探测报告为失败或跳过。
- PaddleOCR 的完整识别依赖本机已可用的运行资源；缺失时不隐式下载，显式探针会报告原因。

## 风险与调整

- 真实桌面输入存在焦点误投递风险，因此默认 Doctor 不发送输入。
- 受控探针只操作自身临时窗口，并在输入前确认目标控件位置；不用于真实业务应用。

## 下周计划

- 实现屏幕截图、OCR 坐标输出和图像预处理模块。
- 建立受控窗口下的点击、输入、滚动和拖拽测试夹具。
- 保持 Doctor 作为后续模块的环境与权限前置检查。
