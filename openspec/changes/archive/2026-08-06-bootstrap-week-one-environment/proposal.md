## Why

项目已完成机器侧的初步核验，但尚无可复现的仓库级环境、模型下载入口和基准记录约定。第一周需要先将这些前置条件固化，才能安全地进入感知、控制和 Agent 的实现。

## What Changes

- 建立 Python 3.12 / Conda `max` 环境的仓库级依赖声明、安装说明和可执行自检。
- 增加 GPU、CUDA、BF16、核心库导入与依赖一致性的诊断入口，输出机器可读的环境证据。
- 增加下载到项目 `model/` 目录且由 Git 排除的 ModelScope 下载脚本，以及本地 `Qwen/Qwen3.5-4B` 单图基准入口。
- 规定实验归档格式，用于保存配置快照、环境信息、显存与延迟结果；模型权重、截图和运行产物不纳入 Git。
- 建立首批 Python 包结构与 Provider/运行配置接口草案，供后续周的感知、控制与 LangGraph 编排接入。

## Capabilities

### New Capabilities
- `runtime-bootstrap`: 可复现地准备、验证并记录 Windows 上的 Python、CUDA/BF16 与项目依赖环境。
- `local-model-benchmark`: 以仓库外的固定缓存下载本地视觉语言模型，并产生可复现的离线单图基准记录。

### Modified Capabilities

无。

## Impact

- 新增 Python 包、命令行入口、依赖锁定/安装材料、环境文档和测试骨架。
- 依赖 PyTorch CUDA 13.0 构建、Transformers、ModelScope、LangChain/LangGraph；视觉和桌面依赖仅做导入与接口层准备。
- 影响本地开发机的 Conda 环境与项目内的 Git-ignored 模型目录 `F:\Coding\max\model`，不引入数据库、Redis、消息队列或网络服务。
