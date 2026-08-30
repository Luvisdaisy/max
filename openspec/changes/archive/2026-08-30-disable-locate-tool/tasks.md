## 1. 默认工具边界

- [x] 1.1 从 `build_default_registry` 移除 `locate_tool` 的默认装配，同时保留底层实现与兼容参数
- [x] 1.2 增加默认 schema 不含 `locate`、调用 `locate` 返回 `unknown_tool` 的回归测试

## 2. Agent 提示词与工具文案

- [x] 2.1 修改 GUI 系统提示词，删除 `locate` / `target_id` 路径，明确截图视图像素和 OCR 使用方式
- [x] 2.2 修改 OCR 工具描述，删除对 `locate` 的推荐并说明直接使用截图坐标
- [x] 2.3 更新 Online-Mind2Web 评测文档，说明默认不暴露控件定位工具

## 3. 验证与文档

- [x] 3.1 更新受影响的 Agent、工具测试，确保测试不再要求默认注册 `locate`
- [x] 3.2 运行 Ruff、相关 pytest、完整 pytest 与 OpenSpec 严格校验（全量 pytest 在受限沙箱中因本地 stub 绑定权限失败；排除该环境测试后 255 项通过）
