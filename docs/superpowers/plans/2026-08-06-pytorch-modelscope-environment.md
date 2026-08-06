# PyTorch + ModelScope Environment Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将第一版运行基线迁移为 Windows Python 3.12 单进程 PyTorch 推理，并用 ModelScope 下载模型、Docker 隔离有状态基础设施。

**Architecture:** LangChain/LangGraph、桌面感知控制与 PyTorch/Transformers 模型推理共同运行在 Windows Conda `max` 环境。ModelScope 只负责下载模型快照，推理始终从固定本地路径加载；PostgreSQL、Redis 等有状态服务仅在项目确有需要时以 Docker Compose 启动。

**Tech Stack:** Python 3.12、PyTorch、Transformers、ModelScope、Qwen2.5-VL-3B-Instruct、LangChain、LangGraph、Docker Compose（按需）

## Global Constraints

- 第一版不安装、不启动 vLLM。
- Conda 环境名固定为 `max`，Python 固定为 3.12。
- 模型下载只使用 ModelScope，不使用 Hugging Face Hub。
- 第一版默认模型为 `Qwen/Qwen2.5-VL-3B-Instruct`，以 BF16 单并发运行。
- 数据库、Redis 等有状态基础设施只能通过 Docker/Compose 引入；无明确需求时不引入数据库。
- 模型权重和缓存不得写入 Git 仓库。

---

### Task 1: 重建 Python 环境

**Files:**
- Modify: Conda environment `F:\Software\Miniconda3\envs\max`

**Interfaces:**
- Consumes: Conda 26.5.3
- Produces: `max` 环境中的 CPython 3.12 与 pip

- [x] 移除当前空的 Python 3.14 `max` 环境。
- [x] 使用 `conda create --name max python=3.12 pip` 重建环境。
- [x] 验证 `sys.version`、解释器路径、SSL 和 SQLite。

### Task 2: 验证部署前置条件

**Files:**
- Modify: none

**Interfaces:**
- Consumes: Windows 驱动、Docker CLI、Python 3.12 包索引
- Produces: GPU、Docker、依赖兼容性检查结果

- [x] 检查 Windows `nvidia-smi` 与 16 GB 显存。
- [x] 检查 `docker version` 和 `docker compose version`；守护进程不可达时明确记录为未就绪。
- [x] 使用 pip dry-run 验证 PyTorch、Transformers、ModelScope、LangChain、桌面感知控制和 PaddleOCR 依赖。
- [x] 安装 PyTorch CUDA 基线并运行 `torch.cuda.is_available()`、设备名、BF16 支持检查。

### Task 3: 更新技术设计

**Files:**
- Modify: `doc/tech-design.md`

**Interfaces:**
- Consumes: Task 1、Task 2 的实测结果
- Produces: 与方案 A 一致的 v1.4 技术设计

- [x] 将 vLLM/WSL 服务架构改为 Windows 单进程 PyTorch/Transformers 架构。
- [x] 将模型获取改为 ModelScope `snapshot_download`，模型从本地固定路径加载。
- [x] 增加 Docker 隔离准则，并明确第一版不为隔离而引入数据库。
- [x] 将环境、测试、风险、目录结构、实施计划和核验表中的旧结论同步更新。

### Task 4: 最终复验

**Files:**
- Verify: `doc/tech-design.md`

**Interfaces:**
- Consumes: 更新后的环境与文档
- Produces: 可审计的最终状态

- [x] 重新运行 Python、PyTorch CUDA、GPU 与 Docker 检查。
- [x] 搜索文档中的 `vLLM`、`Hugging Face`、`Python 3.14` 等旧主线描述，确保只保留历史/后续选项语义。
- [x] 运行 `git diff --check` 并报告用户已有的无关工作区变化，不修改它们。
