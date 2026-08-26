## 1. 微调准备

- [x] 1.1 确认 `artifacts/datasets/screenagent/processed/train.jsonl` 和 `test.jsonl` 存在
- [x] 1.2 实现 `scripts/train_lora.py`（或直接使用 Hugging Face Trainer）
- [x] 1.3 配置 LoRA 参数（rank 64、alpha 32 等）

## 2. 训练执行

- [x] 2.1 启动 vLLM 服务
- [x] 2.2 运行训练脚本（3-5 epochs）
- [x] 2.3 合并 LoRA 权重到 `model/qwen3.5-4b-lora/`

## 3. 评估与部署

- [x] 3.1 跳过（用户明确决定；当前服务只提供 LoRA 模型，未产出基础模型与 LoRA 的对比结论）
- [x] 3.2 调整 `remote`：不要求或发送 `MAX_PROVIDER_KEY`，同步更新 `.env.example`、README 与单元测试
- [x] 3.3 将 macOS `.env` 配置为 `remote`、`qwen3.5-4b-lora` 与 `http://192.168.1.158:8000/v1`
- [x] 3.4 在真实 macOS 上验证 `/health`、`/v1/models` 及一次带工具定义的流式 `/v1/chat/completions`；记录模型响应、finish reason 与实际工具调用结果

## 验证记录

- 2026-08-26：macOS 经 `http://192.168.1.158:8000` 调用 `/health` 返回
  `{"status":"ready"}`，`/v1/models` 返回 `qwen3.5-4b-lora`。
- 2026-08-26：项目 `InferenceClient` 使用 `remote`、不带 `Authorization`、内存生成的
  64×64 纯白 PNG 与 `screenshot` 工具定义完成一次流式调用；结果为空正文、
  `finish_reason=stop`、`tool_calls=[]`、无 usage。该记录证明端到端传输可用，不表示
  工具调用成功。
