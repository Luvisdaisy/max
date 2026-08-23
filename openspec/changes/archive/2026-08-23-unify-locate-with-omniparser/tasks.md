## 1. 配置与运行时

- [x] 1.1 在 Settings 增加 OmniParser 权重目录、base_url（默认 127.0.0.1:8002）、启动/推理超时，并写入 `.env.example`
- [x] 1.2 实现 `LocateRuntime`：懒启动独立 worker、健康检查、加锁复用、只杀自拉进程、失败可注入假客户端
- [x] 1.3 实现 worker 入口：加载 `model/omniparser` 的检测（及可选 caption），提供 `POST /parse`，caption 失败仍回框

## 2. 定位工具

- [x] 2.1 抽出画编号框与投影到 view/logical 的共用函数
- [x] 2.2 实现 `locate`：默认当前视图帧、路径校验、NMS 与最多 40 框、回注 JSON+图、覆盖 `locate_hits`
- [x] 2.3 从默认注册表移除 `ocr_locate` 与对外 spotting 工具，保留整图 `ocr`
- [x] 2.4 更新 `lookup_locate_hit` 与 `mouse_move` 描述，使 `target_id` 指向 `locate`，仍接受 `x/y`

## 3. 会话与契约

- [x] 3.1 成功的模型 `screenshot` 与动作后置截图清空 `locate_hits`；`mouse_move` 核验截图不清空
- [x] 3.2 更新 GUI 系统提示：优先 `locate` 的 `target_id`，抄字用 `ocr`，不再提 `ocr_locate`

## 4. 测试与规范

- [x] 4.1 用假检测器覆盖成功画框、省略 path、截断 40、越权、失败跳过、未知 `ocr_locate`、截图清空 hits、移鼠保留 hits
- [x] 4.2 运行 ruff format / check，并跑相关 pytest
- [x] 4.3 worker 日志落到 `artifacts/logs/omniparser.log`，跳过文案附失败原因；启动只加载 YOLO
- [x] 4.4 在 worker 解释器中安装 `ultralytics`
