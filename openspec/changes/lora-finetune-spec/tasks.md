## 1. 微调准备

- [x] 1.1 确认 `artifacts/datasets/screenagent/processed/train.jsonl` 和 `test.jsonl` 存在
- [x] 1.2 实现 `scripts/train_lora.py`（或直接使用 Hugging Face Trainer）
- [x] 1.3 配置 LoRA 参数（rank 64、alpha 32 等）

## 2. 训练执行

- [x] 2.1 启动 vLLM 服务
- [ ] 2.2 运行训练脚本（3-5 epochs）
- [ ] 2.3 合并 LoRA 权重到 `model/qwen3.5-4b-lora/`

## 3. 评估与部署

- [ ] 3.1 运行 `scripts/eval_lora.py` 对比微调前后效果
- [ ] 3.2 更新 `.env` 或 config.py 中的 MODEL_NAME
- [ ] 3.3 验证在真实 macOS 上工具调用正常
