## Why

4B 几乎做不了绝对像素 grounding，却仍靠猜 `x/y` 点图标；现有 `ocr_locate` 只框文字行，Dock 与无字控件没有可点编号。需要把文字定位与 UI 检测合成一个全屏编号工具，让模型选 `target_id`，坐标由检测器给出。

## What Changes

- **BREAKING**：默认注册表移除 `ocr_locate`。模型再调用该名视为未知工具。
- 新增只读工具 `locate`：对最近全屏截图（或给定 `path`）跑 OmniParser，画最多 40 个编号框，回注带框图与 JSON，并把编号到逻辑中心写入现有 `locate_hits`。
- OmniParser 独立进程：首次 `locate` 再启动，不进主 vLLM / OCR vLLM，项目运行时不安装 torch。检测失败可跳过；Florence caption 失败则只保留框与 OCR 标签。
- 整图 `ocr`（PaddleOCR-VL `OCR:`）保留，专管抄字，不画框。
- `mouse_move` 的 `target_id` 改为命中最近一次成功 `locate`；仍接受裸 `x/y`，不禁止猜坐标。
- 新的成功全屏截图清空 `locate_hits`，避免旧编号点到新画面。
- 系统契约改为：点控件优先 `locate` 再 `target_id`；看不清字再 `ocr`。

## Capabilities

### New Capabilities

- `ui-locate`：OmniParser 懒启动、全屏编号定位工具 `locate`、框上限与命中表写入。

### Modified Capabilities

- `ocr-tool`：删除 `ocr_locate` / `Spotting:` 对外工具；保留整图 `ocr` 与其独立 OCR 服务。
- `agent-tools`：默认注册 `ocr` 与 `locate`，不再注册 `ocr_locate`。
- `desktop-gui-tools`：`target_id` 来自 `locate`；成功全屏截图清空定位表；裸坐标仍可用。
- `react-agent`：系统契约改为优先 `locate` 的 `target_id`，抄字用 `ocr`。
- `session-store`：`locate_hits` 由成功 `locate` 写入；新全屏截图后视为空表直至下次定位。

## Impact

- 工具：`src/max_gui/tools/ocr.py`、`registry.py`、`desktop.py`；新增 OmniParser 运行时（`inference/` 旁，对齐 `OcrRuntime` 生命周期）。
- Agent：`src/max_gui/agent/prompts.py`。
- 配置：OmniParser 权重目录、监听地址、启动/推理超时；端口避开 `:8000` / `:8001`。
- 依赖：检测走独立解释器与 `model/` 下 OmniParser 权重；项目 `.venv` 不新增 torch / ultralytics。
- 测试：假检测后端覆盖画框、截断 40、默认 path、失败跳过、截图清空 hits、未知 `ocr_locate`；CI 不拉真实 OmniParser。
- 文档：`README.md` 在归档后更新（实现期可先改代码与规格）。
