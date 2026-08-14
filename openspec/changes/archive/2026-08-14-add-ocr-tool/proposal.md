## Why

Qwen VL 已经能看见 `screenshot` 回注的屏幕，但小字、密表格、对比度差的界面经常读不准。需要一个只在模型不自信时调用的补充 OCR 工具，用已下载的 PaddleOCR-VL-1.5 给出更可靠的整图文字，而不是再猜一遍画面。

## What Changes

- 新增 Function Calling 工具 `ocr`：对一张已有图像做整图文字识别，结果以文本回到 `observe` / 下一轮 `think`
- 第一版只做整图 `OCR:`，不做 spotting、版面检测、表格/公式/印章任务
- OCR 推理与主模型分离：第一次调用 `ocr` 时再启动独立 vLLM（默认另一端口），不改现有 `max-gui serve` 的单模型 Qwen 进程
- 启动或调用 vLLM 失败时，阻塞地回退到本机 transformers 加载 `model/paddleocr-vl-1.5`；transformers 也失败则工具返回可跳过的中文错误，Agent 继续，不得中断回合
- 图像路径允许 `artifacts/screenshots/` 与工作区，禁止任意系统路径
- 不引入完整 PaddleOCR 文档解析管线，不把 OCR 模型接到主 ReAct / tool calling

## Capabilities

### New Capabilities

- `ocr-tool`：整图 OCR 工具的输入范围、任务面、懒启动 vLLM、transformers 回退与失败跳过

### Modified Capabilities

- `agent-tools`：默认工具注册表必须包含 `ocr`；该工具不走破坏性确认门

## Impact

- 代码：`src/max_gui/tools/` 新增 OCR 工具；`registry.py` 默认注册；可能新增 OCR 客户端与懒启动生命周期（与现有 `lifecycle.serve_model` 分离）
- 配置：OCR 权重目录、独立 `base_url`/端口、超时；不改变默认 Qwen `base_url` `:8000`
- 依赖：OCR 热路径走已有独立 vLLM 环境；transformers 回退若需新依赖，不得污染主 Agent 的 tool-calling 路径，也不得把 PaddlePaddle 拉进项目 `.venv`
- 资源：首次 `ocr` 会拉起约 0.9B 的第二推理进程，需降低其显存占用，避免挤掉已在跑的 Qwen
- 文档：`README.md` / `AGENTS.md` 在实现归档后同步；`docs/gui-tools.md` 中「不做 OCR」的旧结论将被本变更取代
