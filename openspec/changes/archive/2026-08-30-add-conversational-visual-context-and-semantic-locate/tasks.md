## 1. 会话级只读视觉上下文

- [x] 1.1 为 `Session`、加载 / 保存和 checkpoint 增加可选的会话级只读视觉上下文，并保持旧 JSON 安全兼容
- [x] 1.2 在每个新用户回合提取最近可读观察和有限非 reasoning 对话摘要，同时清空上一任务的执行帧、命中表与可执行事实
- [x] 1.3 调整任务上下文和系统提示，明确历史观察仅用于理解；新桌面动作必须先取得当前截图
- [x] 1.4 调整上下文选择、图片编码和预算诊断，实现用户附件、当前观察、历史观察的单图优先级

## 2. 查询驱动的语义视觉定位

- [x] 2.1 扩展 `locate` schema、参数校验和结果格式，支持目标名称查询及 Dock 区域限定，同时保持无参数调用兼容
- [x] 2.2 为 OCR / icon caption 初始化、推理、标签匹配和退化定义机器可读状态及中文安全摘要，禁止把泛化标签伪装为目标
- [x] 2.3 实现唯一可信候选过滤、名称别名规范化和有限事实写入；歧义、无匹配与观察专用图不得产生可执行编号
- [x] 2.4 保持语义候选与现有 `ViewFrame`、`locate_hits`、`mouse_move` 后置截图和无坐标点击门禁一致

## 3. macOS Dock 语义发现

- [x] 3.1 新增 macOS 只读辅助功能适配层，检查权限并读取 Dock 应用的标题、角色和边界，不执行 AX 动作
- [x] 3.2 将唯一且可投影到当前帧的 Dock 应用候选接入语义定位；无权限、不支持、屏幕外或歧义时安全回退视觉定位
- [x] 3.3 记录不含标题正文、截图或敏感输入的语义发现 / 回退诊断，并向 TUI 返回中文状态

## 4. 测试与文档

- [x] 4.1 为会话恢复、历史图追问、用户附件优先、缺图降级和新动作不可复用旧编号增加单元 / 集成测试
- [x] 4.2 为查询定位的唯一匹配、泛化标签、caption 不可用、歧义候选、历史图仅观察和既有坐标核验增加测试
- [x] 4.3 使用 mock accessibility 覆盖 macOS Dock 的成功、无权限、不支持、屏幕外与不执行 AX 动作；在真实 macOS 上完成 Chrome Dock 冒烟并单独标注结果

验证记录：2026-08-30 在本机 macOS 执行只读 Dock 查询，结果为 `accessibility_unavailable`，未发现 Chrome 候选；未执行任何 AX 动作，实现按设计安全降级。
- [x] 4.4 更新 README 的会话视觉上下文、辅助功能权限、视觉回退和安全边界说明
- [x] 4.5 运行 `uv run ruff format src tests`、`uv run ruff check src tests`、相关 pytest、完整 pytest 与 `openspec validate add-conversational-visual-context-and-semantic-locate --strict`
