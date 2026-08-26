## 1. 坐标帧与命中表

- [x] 1.1 为定位结果区分当前截图帧与观察专用图像，非当前帧成功定位时清空命中表并返回明确坐标空间。
- [x] 1.2 调整 `project_and_draw` 与 `locate`，仅为当前截图帧生成可执行的逻辑中心和 `target_id` 命中。
- [x] 1.3 更新 `mouse_move`、`mouse_scroll` 的错误文案与保护，拒绝观察专用定位的编号。

## 2. 带框图回注一致性

- [x] 2.1 建立带框图最终发送尺寸的单一决策点，避免推理层二次缩放导致 JSON 坐标失配。
- [x] 2.2 为字节上限触发的缩小分支同步重投影框图与坐标，或返回可恢复错误。

## 3. Worker 地址边界

- [x] 3.1 校验 OmniParser base URL 为 loopback 地址，拒绝远端本地路径 worker。
- [x] 3.2 更新 `.env.example` 与工具说明，说明本机 worker 和显式路径的观察限制。

## 4. 验证

- [x] 4.1 添加 2× 高 DPI 当前截图、历史截图、带框副本和失效编号的定位/桌面工具测试。
- [x] 4.2 添加叠加图在字节上限下的发送尺寸与 JSON 坐标一致性测试，以及远端 worker 地址拒绝测试。
- [x] 4.3 运行 `uv run ruff format src tests`、`uv run ruff check src tests` 与相关 pytest。
