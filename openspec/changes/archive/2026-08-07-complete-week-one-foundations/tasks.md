## 1. Doctor 环境与工具验证

- [x] 1.1 将命令行和聊天入口从 `diagnose`/`/diagnose` 重命名为 `doctor`/`/doctor`，移除旧公开别名，并更新帮助文本与测试。
- [x] 1.2 扩展 Doctor 结果模型和渲染，分组展示 Python、依赖、CUDA/GPU、BF16 与基础工具的通过、失败、跳过状态，同时保留不含模型信息的结构化 artifact 结果与非零失败语义。
- [x] 1.3 实现默认无输入的 mss 内存截图、OpenCV 合成图像、PaddleOCR 本地可用性、PyAutoGUI 只读屏幕信息和 pynput 可用性探测；为缺失依赖、非交互桌面和探测失败提供明确诊断。
- [x] 1.4 实现显式 `--desktop-probe`：在临时受控窗口中验证截图、非敏感 OCR 样例、点击与输入，并在窗口校验失败时阻止输入。
- [x] 1.5 为 Doctor 重命名、可读输出、各项探测、显式桌面探针、无输入默认路径与模型字段排除补充单元和受控集成测试。

## 2. 第一周交付材料

- [x] 2.1 更新 README；`docs/environment.md` 已由用户删除并按指示跳过，README 说明 Doctor 的运行环境、基础工具验证顺序和证据位置，并删除 Diagnose 指令。
- [x] 2.2 新增 `docs/week1/weekly-report.md`，按项目周报模板汇总调研/架构引用、Doctor、环境证据、已知限制、风险与第二周接口前置条件。
- [x] 2.3 核对 CLI 帮助、README、环境指南和周报的命令与 artifact 位置一致，且不披露模型信息、真实截图、个人数据或密钥。

## 3. 验证与交付

- [x] 3.1 运行 `python -m unittest discover -s tests -v` 与 `python -m pip check`。
- [x] 3.2 在目标 `max` 环境运行 Doctor；仅在交互式授权会话执行桌面探针，将产生的非模型证据保留在 Git 忽略的 `artifacts/`，并在周报中记录结果或明确失败原因。
- [x] 3.3 运行 `npx.cmd --yes @fission-ai/openspec@1.8.0 validate --specs` 和变更校验，确认规格、文档和实现均可交接。
