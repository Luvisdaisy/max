## Context

主 Agent 已经通过 `screenshot` 把屏幕图回注给 Qwen VL。2B 看小字、密表格、低对比界面经常不稳。`model/paddleocr-vl-1.5` 已在仓库（约 0.9B，`PaddleOCRVLForConditionalGeneration`）。本机 `~/.venv-vllm-metal` 的 vLLM 0.27.1 已注册该架构。

现有 `max-gui serve` 是单进程、单模型、`:8000`、`--tool-call-parser qwen3_coder`、`gpu_memory_utilization=0.85`。vLLM 不能在同一进程里再挂一个异构模型。项目 `.venv` 没有 torch / transformers / PaddlePaddle，也不该为 OCR 回退把它们拉进来。

## Goals / Non-Goals

**Goals:**

- 新增只读工具 `ocr`，对一张图做整图文字识别，结果以纯文本回 ReAct
- 第一次调用时再启动独立 OCR vLLM；之后复用该进程
- vLLM 不可用时，阻塞地用同一套独立推理环境跑 transformers；仍失败则返回可跳过错误，图继续
- 路径只允许截图目录与工作区

**Non-Goals:**

- spotting、表格/公式/图表/印章、PP-DocLayoutV2、完整 PaddleOCR 管线
- 把 OCR 模型接入主 ReAct 或 tool calling
- 改 `max-gui serve` 为多模型，或默认同时拉起两个服务
- 每次截图自动 OCR
- 在项目 `.venv` 安装 PaddlePaddle / torch

## Decisions

### 1. 独立第二服务，而不是塞进现有 serve

官方 recipe 是单独 `vllm serve`，参数与 Qwen 冲突：`--trust-remote-code`、`--no-enable-prefix-caching`、`--mm-processor-cache-gb 0`，且不要 `qwen3_coder`。

备选：共进程多模型（本机 0.27.1 的 `serve` 不支持）；进程内加载进 TUI（会卡住 UI、污染依赖）。不采用。

默认：权重 `model/paddleocr-vl-1.5`，`--served-model-name paddleocr-vl-1.5`，主机 `127.0.0.1`，端口 `8001`（可用环境变量覆盖）。`gpu_memory_utilization` 明显低于主模型（建议约 `0.20`），避免和已占用 85% 的 Qwen 抢统一内存。解析 vLLM 二进制的规则与 `serve` 相同。

### 2. 第一次调用再启动，进程常驻

不在 `max-gui` / `max-gui serve` 启动时拉 OCR。`ocr.invoke` 里 `ensure_ocr_server()`：已健康则直接请求；否则用同一套 vLLM 二进制拉起子进程，轮询 `/v1/models` 或等价就绪条件，带启动超时。并发第一次调用必须加锁，只起一个进程。

进程挂在模块级运行时上，TUI 退出时尽量终止，避免孤儿占用端口。不把 OCR 生命周期绑到 Qwen serve。

### 3. 调用约定：整图 `OCR:`

按 recipe / 模型 README，对 OpenAI 兼容接口发一条 user 消息：本地图的 `image_url`（data URL，复用现有图像预处理上限）+ 文本 `OCR:`。`temperature=0`。不传 tools。

工具参数第一版只有 `path`。描述用中文写明：仅在主模型看不清字或需要精确抄录时调用，禁止每轮截图后无条件 OCR。

返回纯文本识别结果。不回图、不要确认门。

### 4. 路径：截图目录 ∪ 工作区

`screenshot` 写在 `artifacts/screenshots/`，现有 `resolve_workspace_path` 会拒。`ocr` 使用单独解析：绝对或相对路径必须落在 `screenshots_dir` 或 `workspace` 之内。缺文件、越权返回中文工具错误，不启动推理。

### 5. 回退链：vLLM → transformers 子进程 → 跳过

```
ocr(path)
  │ 校验路径
  ├─ 确保 OCR vLLM 就绪并 POST /chat/completions
  │     成功 → 返回文本
  ├─ 失败 → 用 vLLM 环境的 python 子进程跑 transformers
  │     加载本地 model/paddleocr-vl-1.5，prompt「OCR:」
  │     成功 → 返回文本（注明走了回退，便于排查）
  └─ 仍失败 → 返回中文「OCR 不可用，请仅根据已有截图继续」，不抛出图外
```

transformers 必须走独立解释器（`vllm` 二进制同目录的 `python`），用 `asyncio.to_thread` / 子进程，避免把 torch 打进项目依赖，也避免堵死 Textual 循环。回退是阻塞的：当前这次 `ocr` 等它结束；启动或推理超时视为失败，进入下一档。

不把「CPU 版 PaddleOCR」或「再下一个引擎」列为第三档。

### 6. 模块边界

- `tools/ocr.py`：schema、路径、回退编排、注册用的 `Tool`
- OCR HTTP 客户端与懒启动：`inference/` 或 `lifecycle` 旁的小组件，不要塞进 `InferenceClient`（那个绑定主模型、流式、tools）
- `registry.build_default_registry` 追加 `ocr`
- 配置项进 `Settings`：OCR 端口 / `base_url`、权重目录、启动超时、推理超时、OCR `gpu_memory_utilization`

测试：假 HTTP / 假启动器覆盖成功、vLLM 失败后 transformers 成功、两档都失败跳过、路径越权；不在 CI 里真拉 vLLM 或 Metal。

## Risks / Trade-offs

- [Metal 上 PaddleOCR-VL-1.5 的 vLLM 可能起不来] → 规范要求回退 transformers；两者都失败则跳过，主 Agent 仍可用
- [主模型已占 85% 统一内存，第二进程 OOM] → OCR 进程用更低 `gpu_memory_utilization`；仍失败走 transformers 或跳过
- [首次调用很慢] → 接受；超时后降档，不无限等
- [截图带红色光标十字，可能污染 OCR] → 第一版接受；需要更干净画面时由模型先对 `region` 再截图
- [模型每轮都调 `ocr`，烧迭代次数] → 工具描述约束；不做服务端限流
- [TUI 异常退出留下 OCR 进程] → 尽量 `atexit` / 应用关闭时杀进程；端口固定，下次启动可复用已健康的实例

## Migration Plan

- 纯增量：不注册 `ocr` 即回到现状
- 不改已有会话 JSON schema
- 归档后更新 `README.md`、`AGENTS.md`，并修正 `docs/gui-tools.md` 里「不做 OCR」的表述

## Open Questions

- 无。启动时机、任务面、回退策略已由探索结论锁定。
