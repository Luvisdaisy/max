# 第一周文档交付 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为组内 mentor 提供技术调研报告、完整系统架构报告，以及整合至 README 的可复现环境指南。

**Architecture:** 将技术比较、系统设计和操作说明拆分到职责单一的 Markdown 文件。调研报告解释选型依据；架构报告以 Mermaid 描述完整闭环及前四周交付如何接入；README 提供与仓库 CLI 和目录约定一致的环境操作路径。

**Tech Stack:** Markdown、Mermaid、PowerShell、项目 CLI `max-agent`、Conda、PyTorch CUDA 13.0。

## Global Constraints

- 文档使用中文，面向组内具备工程背景的 mentor。
- 不提供来源标注，不按“已验证/待完成”分类。
- 不写入模型权重、密钥、真实截图或个人数据。
- 模型位于仓库根目录 `model/`，运行证据位于被 Git 忽略的 `artifacts/`。
- 桌面控制仅限受控测试环境，并受 Safety Guard、会话锁和显式开关约束。

---

### Task 1: 编写技术调研报告

**Files:**
- Create: `docs/week1/research-report.md`
- Test: Markdown 人工结构检查

**Interfaces:**
- Consumes: 项目技术路线、四周任务范围、ScreenAgent/UI-TARS/WebArena 的设计要点。
- Produces: 供架构报告引用的项目技术取舍，包括闭环、动作表示、验证和可复现评测原则。

- [ ] **Step 1: 创建报告骨架**

建立“摘要、问题定义、方案比较、项目技术取舍、前四周落地重点、风险与结论”六个一级章节；确保比较对象固定为 ScreenAgent、UI-TARS、WebArena。

- [ ] **Step 2: 填充横向比较表**

用表格逐项比较感知输入、规划/执行机制、动作空间、验证方法、评测环境、适用边界与工程启示；每行给出本项目的具体采纳或不采纳决定。

- [ ] **Step 3: 编写项目取舍与四周落地内容**

明确项目采用“模型提出候选动作 + 确定性 Guard 放行 + 执行后验证”的闭环，列出第一至四周分别提供的环境、感知控制、基础 Agent 和端到端集成能力。

- [ ] **Step 4: 审阅报告**

检查所有三个比较对象均被覆盖；确认调研结论没有把 WebArena 误写为桌面自动化控制框架，且不含来源标注或阶段性状态分类。

### Task 2: 编写完整系统架构报告

**Files:**
- Create: `docs/week1/architecture-report.md`
- Test: Mermaid 语法与 Markdown 人工检查

**Interfaces:**
- Consumes: Task 1 的组合式技术取舍与项目现有数据契约。
- Produces: 从 CLI 输入到证据归档的完整模块边界、数据流和安全策略说明。

- [ ] **Step 1: 创建系统范围和架构图**

编写系统目标、运行边界和 Mermaid 流程图，图中至少包含 CLI、Orchestrator、Perception、Agent State、ModelProvider、Planner、Safety Guard、Controller、Verifier、Recovery、Artifact Store。

- [ ] **Step 2: 编写模块边界与数据契约**

以表格说明每个模块的职责、输入、输出和禁止承担的职责；定义 Observation、DesktopAction、ApprovedAction、ExecutionReceipt、StepRecord 的字段语义与坐标约定。

- [ ] **Step 3: 编写前四周交付映射与运行策略**

用表格把环境基础、感知/控制、基础 Agent、端到端集成映射到架构模块和可验收能力；描述失败、超时、无进展和高风险动作的处理路径。

- [ ] **Step 4: 校验图与文字一致性**

确认图中的所有模块均有文字职责，所有带桌面副作用的路径均经过 Safety Guard，且架构报告以完整系统组织而非分周报告组织。

### Task 3: 更新 README 环境配置指南

**Files:**
- Modify: `README.md`
- Test: PowerShell 命令与路径人工检查

**Interfaces:**
- Consumes: 仓库依赖清单、CLI 命令和 `model/`、`artifacts/` 目录约定。
- Produces: 新开发者可按顺序执行的安装、诊断、模型下载、离线基准和排障说明。

- [ ] **Step 1: 组织环境准备与安装步骤**

说明 Windows 11、Conda `max`、Python 3.12、NVIDIA GPU 的前置条件，并给出以下安装顺序：

```powershell
conda activate max
python -m pip install --index-url https://download.pytorch.org/whl/cu130 -r requirements/torch-cu130.txt
python -m pip install -r requirements/base.txt
python -m pip install -e .
```

- [ ] **Step 2: 增补诊断、模型与基准命令**

加入 `max-agent --artifact-root artifacts diagnose`、`max-agent validate-model`、`modelscope download` 和 `max-agent benchmark` 的使用条件及命令示例；说明离线基准不允许隐式联网下载。

- [ ] **Step 3: 增补归档与排障章节**

列出 `config.yaml`、`environment.json`、`trajectory.jsonl`、`result.json` 的归档约定；分别给出 CUDA/BF16、依赖冲突、模型缺失和桌面会话限制的排查动作。

- [ ] **Step 4: 校验 README 可复现性**

检查命令、路径和模型 ID 与仓库现有配置一致；检查 README 未暗示可以执行无保护的桌面控制。

### Task 4: 最终文档验证

**Files:**
- Verify: `docs/week1/research-report.md`
- Verify: `docs/week1/architecture-report.md`
- Verify: `README.md`

**Interfaces:**
- Consumes: Tasks 1–3 生成的 Markdown 文档。
- Produces: 可交付的、一致的第一周文档集。

- [ ] **Step 1: 执行结构检查**

用 PowerShell 检查三个文件存在、标题层级完整、Markdown 代码围栏成对出现；使用文本搜索检查没有 `TODO`、`TBD`、密钥示例或来源标注章节。

- [ ] **Step 2: 执行交叉一致性检查**

逐项确认模型目录为 `model/`、证据目录为 `artifacts/`、CLI 为 `max-agent`，并确认技术调研报告、架构报告和 README 对安全边界的叙述一致。

- [ ] **Step 3: 审阅 Git 变更范围**

运行 `git status --short`，确认本次新增或修改限定为 `docs/week1/`、`README.md` 和本次过程生成的设计/计划文档；不触碰现有未提交改动。
