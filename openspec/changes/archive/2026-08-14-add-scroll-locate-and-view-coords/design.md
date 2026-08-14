## Context

桌面工具已经能截主屏、移鼠、点按、拖拽、输入。OCR 只能整图 `OCR:` 回纯文本。规格把滚轮和 spotting 都标成不做。

线上点不准，不是 PyAutoGUI 随机漂移，而是三条坐标系叠在一起，却只让模型「用逻辑像素」：

```
逻辑屏        例如 1440×900
    × scale（Retina 常为 2）
落盘 PNG      例如 2880×1800     ← screenshot 摘要却写 width=1440
    × prepare_image（最长边 1536，过大还可能再减半）
模型看见的图  例如 1536×960      ← 模型按这张图估 (x, y)
    → mouse_click 把该数当逻辑像素执行
```

常见打偏方式：

1. 按「看见的图」给点，工具当逻辑像素用。逻辑宽 / 视图像素宽不是 1，整体比例错。
2. 按落盘 PNG 像素给点（约 2 倍），再被夹到屏幕边缘。
3. 按 Qwen 常见的 0–1000 归一化给点，点击挤在左上角。
4. `region` 截图后用局部坐标当全局坐标。
5. 2B 本身点不准；没有文字框时只能猜。

约束：继续用现有 `Tool` 协议、PyAutoGUI、独立 OCR vLLM / transformers 回退；项目 `.venv` 不加 PaddlePaddle / 检测模型；CI 仍走假后端。

## Goals / Non-Goals

**Goals:**

- 增加 `mouse_scroll`
- 增加 `ocr_locate`：`Spotting:` → 编号框图 + 可点中心
- 桌面坐标改为视图像素：模型给「看见的图」上的点，工具换算成逻辑像素
- `screenshot` 摘要带上视图宽高与区域原点，换算可测、可测

**Non-Goals:**

- Windows / Linux 一等支持
- OmniParser、OpenCV `locateOnScreen`、辅助功能树
- 表格 / 公式 / 图表 / 印章任务
- 横向滚动、多显示器
- 每次截图自动 OCR
- 单独的《单元测试报告》文档

## Decisions

### 1. 鼠标输入改成视图像素，由工具换算

视图像素 = `prepare_image` 真正发给主模型的那张 JPEG 的宽高。换算：

```
logical_x = origin_x + round(view_x * frame_logical_w / view_w)
logical_y = origin_y + round(view_y * frame_logical_h / view_h)
```

全屏时 `origin` 为 `(0, 0)`，`frame_logical_*` 为主屏逻辑尺寸。`region` 时 `origin` 为区域左上角逻辑坐标，`frame_logical_*` 为区域逻辑宽高。

换算所需的「上一张截图坐标系」放在与 `current_session_id` 同级的上下文里，由成功的 `screenshot` 写入。`mouse_*` 读取它。尚无截图时，把输入当作逻辑像素并在结果里说明，避免冷启动卡死。

- 备选：继续让模型用逻辑像素，只把 `scale` 写得更醒目。不采用：2B 会按看见的图点，文案约束无效。
- 备选：把落盘 PNG 缩成逻辑分辨率，使 1 图像素 = 1 逻辑像素。不单独采用：逻辑边仍可能超过 `max_image_edge`，region 仍有局部原点问题。作为「视图碰巧等于逻辑」的特例可以出现，但不能当唯一契约。
- 备选：启发式识别 0–1000。不采用：与真实逻辑坐标重叠，会误伤。

### 2. 预处理与截图摘要共用同一套缩放

`prepare_image` 必须同时给出编码后的 `width` / `height`（质量循环一般不改尺寸，超字节时的减半会改）。截图摘要里的 `view_width` / `view_height` 必须用同一函数，不能各算各的。

摘要字段（在现有 `path` / `scale` / `cursor` 之外）：

- `logical_width` / `logical_height`（或沿用现有 `width` / `height` 表示逻辑尺寸，并新增视图字段）
- `view_width` / `view_height`
- `origin`: `{x, y}` 逻辑原点
- `coordinate_space`: `view`（告诉模型：点鼠标请用视图像素）

工具描述同步改成「x/y 是你看到的这张截图上的像素，原点在图左上」。

### 3. 滚轮做成普通桌面工具

`DesktopBackend.scroll(clicks, x=None, y=None)`。生产实现走 `pyautogui.scroll`；正数向上。给出 `x`/`y` 时先按视图像素换算再滚。

`mouse_scroll` 参数：`clicks`（必填整数）、可选 `x`/`y`/`duration`。`confirmation_scope="desktop"`，与点击同级（会改变页面）。不做 `hscroll`。

### 4. 定位用新工具 `ocr_locate`，不改 `ocr` 的返回形

`ocr` 继续只回纯文本、提示 `OCR:`。`ocr_locate`：

- 路径规则与 `ocr` 相同（截图目录 ∪ 工作区）
- 不确认
- 同一套 `OcrRuntime`，提示改为 `Spotting:`
- spotting 单独加大 `max_new_tokens`（建议 ≥ 2048），避免整屏文字行被截断
- 官方对小图的 2× 上采样只在原图两边都小于 1500 时做，并记下倍数，框必须映回原图像素
- 解析失败或两档推理都失败：中文可跳过错误，不抛出图外
- 成功则在**视图尺寸**的副本上画编号框（保证回注后编号仍可读），返回 `ToolResult`：JSON + 带框图

JSON 每项：`id`、`text`、`view`（x/y/w/h/cx/cy）、`logical`（同上）。`cx/cy` 为框中心。模型应优先抄 `view.cx/cy` 去点。

`mouse_click` / `mouse_move` 增加可选 `target_id`：命中最近一次成功的 `ocr_locate` 结果时，直接用该项的逻辑中心，忽略本次 x/y。2B 抄数字比估像素稳。

- 备选：给 `ocr` 加 `task` 参数。不采用：有时回字符串、有时回带框图，2B 和测试都更难。
- 备选：上 OmniParser 做真控件。不采用：新模型、新进程，超出本周范围。

### 5. spotting 输出格式在实现时钉死，解析失败则关

PaddleOCR-VL README 只保证提示词 `Spotting:`，没有稳定 JSON schema。实现顺序：

1. 用夹具图打一次 vLLM 或 transformers，把原文样例写进测试。
2. 解析器覆盖实际样例，以及常见的框标记 / JSON 列表。
3. 无法解析则返回中文错误，不要编造框。

`OcrRuntime.recognize` / transformers worker 增加 `prompt`（及可选 `max_new_tokens`），默认仍为 `OCR:`，避免改坏现有 `ocr`。

## Risks / Trade-offs

- [Risk] 2B 仍乱报坐标 → 视图像素对齐「看见的图」；`ocr_locate` + `target_id` 提供第二条路径。
- [Risk] spotting 文本格式不稳定 → 先采样再写解析；失败可跳过。
- [Risk] 整屏 spotting 慢、token 不够 → 加大生成长度；工具描述要求先 `region` 再 locate。
- [Risk] 无字图标框不到 → 规格写明只框文字行；图标仍靠主 VL 看带框图或原截图。
- [Risk] 上一张截图坐标系过期（滚动或切窗后仍用旧原点）→ 换算前不自动重截；结果提示「基于最近一次 screenshot」；模型应在滚动后重新截图。
- [Risk] 主模型与 OCR 同时占统一内存 → 沿用现有懒启动与低 `gpu_memory_utilization`。
- [Risk] 旧会话里的模型习惯逻辑坐标 → 摘要与 schema 改为 `coordinate_space=view`；这是对模型的行为破坏，可接受。

## Migration Plan

- 纯增量工具：`mouse_scroll`、`ocr_locate`。不注册即无滚轮/定位。
- 坐标契约改变后，旧提示词会短暂不准，以新摘要为准。
- 不改会话 JSON schema。
- 回滚：去掉两个新工具，并把鼠标输入改回逻辑像素即可。

## Open Questions

- spotting 的具体文本格式以实现时夹具采样为准，不在设计阶段锁死正则。
