## Context

4B 点图标时仍猜视图像素；`ocr_locate` 只框文字行，且与拟议 UI 框抢同一张 `locate_hits`。点击需要控件热区中心与可读编号，抄字仍用已有 PaddleOCR-VL `ocr`。OmniParser（YOLO 检测 + OCR 标签 + 可选 Florence caption）适合作为唯一画框来源。OCR 运行时已是「首次调用再拉独立进程、失败跳过、项目 `.venv` 不进 torch」，定位服务抄同一生命周期，不得再挂一套 vLLM。

## Goals / Non-Goals

**Goals:**

- 默认工具只留一个画框入口 `locate`，由 OmniParser 出框，全屏最多 40 个编号。
- 命中表、`target_id`、视图像素换算、红十字核验复用现有桌面协议。
- `ocr` 继续整图抄字；`ocr_locate` 从注册表消失。
- 检测进程懒启动；caption 失败降级为有框无描述；整次失败可跳过。
- 裸 `x/y` 仍可用。

**Non-Goals:**

- 无障碍树、按名查找、`query` 过滤、强制区域截图。
- 禁止 `mouse_move` 的坐标参数。
- 每次 `screenshot` 自动定位。
- 用 OmniParser 替换整图 `ocr` 或关掉 PaddleOCR 服务。
- 把检测模型塞进主 vLLM / OCR vLLM，或在项目 `.venv` 安装 torch / ultralytics。
- 多屏、找窗、图标模板匹配。

## Decisions

### 1. 对外工具名 `locate`，删除 `ocr_locate`

4B 不能在两套编号里选。`locate` 出控件热区（有字用 OCR 文本当 `label`，没字用 caption 或 `icon`/`button`）。`ocr` 只返回纯文本。调用已移除的 `ocr_locate` 走未知工具错误。

备选：保留 `ocr_locate` 作文字行。否决：整表覆盖会让编号串台；点的时候字形中心也不如热区。

### 2. OmniParser 独立 HTTP 进程，对齐 `OcrRuntime`

`LocateRuntime`：加锁、健康检查、只杀自己拉起的进程、`atexit`。默认 `http://127.0.0.1:8002`。首次合法 `locate` 用独立解释器启动 worker（优先 `MAX_GUI_OMNIPARSER_PYTHON`，否则与 OCR 相同的 vLLM 旁 `python`），加载 `model/omniparserv2/` 下官方 V2 拆分权重（`icon_detect/model.pt`、可选 `icon_caption`；亦兼容旧名 `icon_caption_florence`）。可用 `MAX_GUI_OMNIPARSER_DIR` 覆盖目录名。

Worker 提供 `POST /parse`：收图像字节或本地路径，回框列表（原图像素或归一化，由客户端映回）。TUI 主进程只做 HTTP 与画框，不 import YOLO。

备选：每调一次子进程。否决：加载 Florence 太慢。备选：再起 vLLM 跑 grounding。否决：和 4B/OCR 抢统一内存。

### 3. 全屏默认当前视图帧，上限 40

`path` 可省略：有 `active_view_frame().image_path` 且文件存在则用之。显式 `path` 仍须落在截图目录或工作区。

工具层在画框前：IoU NMS、丢过小框、按检测分数（无分数则按面积）保留至多 40、从上到下从左到右编号。截断掉的框不进 JSON、不画、不写入 hits。无框视为定位失败（可跳过），不画空叠加图。

### 4. 投影与命中表复用 `ocr_locate` 后半段

从 `tools/ocr.py` 抽出「框 → view/logical → 画编号 → `store_locate_hits`」。OmniParser 坐标若在原图上，按与 spotting 相同的 `src → view/logical` 公式映射，避免 `target_id` 系统性偏移。叠加图画在视图尺寸上，与模型看见的截图对齐。

`lookup_locate_hit` 失败文案改为「请先调用 locate」，不再写 `ocr_locate`。

### 5. 何时清空 hits

`mouse_move` 后置截图只加红十字，画面结构未变，**不得**清空 hits（否则核验截图后无法再按编号微调）。模型直接调用 `screenshot`，或点击/拖拽/滚动/输入/按键的后置截图（`verify_source=action`），MUST 清空 `locate_hits` 并写回会话。下一次 `target_id` 必须重新 `locate`。

成功 `locate` 仍整表覆盖。

### 6. 降级链

```
locate
  ├─ 校验 path / 默认视图帧
  ├─ 确保 OmniParser 进程就绪并 POST /parse
  │     YOLO 成功、Florence 失败 → 仍用框 + OCR/空 label
  ├─ 零框或进程失败 → 中文「界面定位不可用，请仅根据已有截图继续」
  └─ 不把异常抛出 ReAct 图外
```

不要求第二套 transformers 回退（权重与 YOLO 绑定在 worker 内）。项目运行时不新增检测依赖。

### 7. 契约只改文案，不禁坐标

系统提示：点图标/按钮优先 `locate` 再 `target_id`；看不清或需抄录再 `ocr`；坐标仍可用最近一帧视图像素。`mouse_move` schema 仍含 `x`/`y`。

定位用图若带红十字，检测可能多出假框。`locate` 对默认帧读取落盘 PNG（含十字）第一版接受；需要干净画面时由模型先 `screenshot` 且 `show_cursor=false`。不在本期自动去十字。

## Risks / Trade-offs

- [本机 4B+OCR+Florence 统一内存不够] → caption 失败则只检测；YOLO 相对小。整次失败则跳过，模型可猜坐标。
- [全屏超过 40 个可点目标] → 丢掉小框；漏检时模型可区域截图后再 `locate`，或猜 `x/y`。
- [OmniParser 内置 OCR 中文弱] → 抄字仍走 PaddleOCR `ocr`；label 不准时 4B 仍可看叠加图选号。
- [旧会话/提示仍写 `ocr_locate`] → 未知工具错误；契约与工具描述改成 `locate`。
- [后置动作截图清空 hits，模型想连点同一编号] → 故意的；画面已变。需再 `locate`。
- [权重未下载] → 首次调用失败并跳过；测试用假 `parse_fn`，CI 不拉权重。
- [worker 解释器缺 ultralytics] → 安装到 vLLM 旁 Python；stderr 写入 `artifacts/logs/omniparser.log`，跳过文案附退出原因。caption / EasyOCR 推迟到首次 `/parse`，避免启动阶段被 Florence 拖死。

## Migration Plan

- 增量：注册 `locate`、去掉 `ocr_locate`。旧会话 `locate_hits` 字段形状不变。
- 回滚：恢复 `ocr_locate` 注册并删除 `LocateRuntime`。
- 权重：用户自行放到 `model/omniparserv2/`；缺失时工具可跳过，不阻断 REPL。
- 归档后更新 `README.md` 工具列表与系统契约简述。

## Open Questions

无。检测器、上限 40、不禁裸坐标、合并画框入口已在探索中锁定。
