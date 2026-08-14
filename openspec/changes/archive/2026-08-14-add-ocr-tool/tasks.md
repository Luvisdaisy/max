## 1. 配置与路径

- [x] 1.1 在 `Settings` 增加 OCR 权重目录、独立 `base_url`/端口、启动超时、推理超时、OCR `gpu_memory_utilization`
- [x] 1.2 实现截图目录 ∪ 工作区的路径解析，越权与缺文件返回中文错误

## 2. OCR 运行时

- [x] 2.1 实现懒启动：首次调用才拉独立 vLLM（`:8001`、`--trust-remote-code`、关 prefix cache、无 Qwen tool parser），健康检查后复用，并发只起一个进程
- [x] 2.2 实现 OCR Chat Completions 客户端：整图 `image_url` + `OCR:`，不传 tools
- [x] 2.3 实现 transformers 回退：用 vLLM 环境的 python 子进程加载 `model/paddleocr-vl-1.5`；两档都失败或超时返回可跳过中文错误
- [x] 2.4 TUI/进程退出时尽量终止本会话拉起的 OCR 子进程；已在监听的健康实例可复用

## 3. 工具注册

- [x] 3.1 实现 `ocr` 工具（参数 `path`，无确认门），编排「校验 → vLLM → transformers → 跳过」
- [x] 3.2 将 `ocr` 加入默认注册表；工具描述写明仅在看不清或需精确抄录时调用

## 4. 测试与规范

- [x] 4.1 用假客户端/假启动器覆盖：成功、vLLM 失败后回退成功、两档失败跳过、路径越权、主 `serve` 不启动 OCR
- [x] 4.2 运行 `uv run ruff format src tests` 与 `uv run ruff check src tests`
