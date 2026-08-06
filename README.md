# MAX desktop-agent prototype

## Chat console

`max-agent` now opens the Textual chat console by default. The console is the local development surface for the future GUI Agent; it currently supports `/diagnose` and `/quit`. Ordinary messages receive an explicit local notice that no AI backend has been configured, and do not load a model or control the desktop.

```powershell
# Start the default Textual chat console
max-agent --chat

# Use the Prompt Toolkit fallback on a constrained terminal
max-agent --fallback

# Run diagnostics without entering a console
max-agent --diagnose --artifact-root artifacts
```

Existing operations remain available as subcommands: `diagnose`, `download-model`, `validate-model`, and `benchmark`.

## Qwen3.5-4B first baseline

The first offline visual benchmark uses `Qwen/Qwen3.5-4B` from `model/Qwen/Qwen3.5-4B` with the native Transformers multimodal loader. It never enables remote code and never falls back to a network download.

```powershell
max-agent --artifact-root artifacts benchmark --model-dir model\Qwen\Qwen3.5-4B --image tests\fixtures\one-pixel.ppm --prompt "Describe this image in one sentence." --max-new-tokens 8
```

On the initial Windows `max` environment run, this command completed with 10.36 s model load time, 1.76 s inference time, and 9.30 GB peak GPU memory. The exact structured evidence is written below the ignored `artifacts/` directory for each run.

面向 Windows 的本地 GUI 智能体原型。项目以“感知—规划—受控执行—验证”为核心闭环；当前命令行工具提供环境诊断、项目内模型下载和离线单图基准。它不提供桌面控制命令。

## 适用环境

项目要求 Python 3.12 和可用的 PyTorch 运行时。GPU 推理与离线视觉基准需要 NVIDIA CUDA 环境，并要求实际支持 BF16 张量运算；CPU 环境可用于安装、导入和单元测试，但不能通过 GPU 诊断或运行 BF16 基准。

Conda 是推荐的隔离方式，但不是唯一选择。可以使用任意虚拟环境管理器，只要最终解释器为 Python 3.12，并且安装了项目固定的依赖版本。

## 安装

创建并激活 Python 3.12 虚拟环境后，在仓库根目录执行：

```powershell
# 可选：使用 Conda 时，环境名称可自行决定
conda create -n <environment-name> python=3.12
conda activate <environment-name>

# 安装与本机 CUDA 驱动兼容的 PyTorch 构建
python -m pip install --index-url <pytorch-wheel-index> -r requirements/torch-cu130.txt
python -m pip install -r requirements/base.txt
python -m pip install -e .
python -m pip check
```

仓库当前提供 CUDA 13.0 对应的依赖清单；若使用其他平台或 CUDA 构建，请先按 PyTorch 官方兼容矩阵选择相应 wheel，再确保 `torch` 与 `torchvision` 版本与项目依赖一致。其余 Python 包由 `requirements/base.txt` 和 `pyproject.toml` 固定。

## 环境诊断

```powershell
max-agent --artifact-root artifacts diagnose
```

该命令会记录 Python、包导入、CUDA 可用性、CUDA 运行时、真实 BF16 GPU 张量运算和依赖一致性。失败时以非零状态退出，且不会加载模型、启动服务或执行桌面操作。

## 模型目录与基准

模型必须放在项目根目录、受 Git 忽略的 `model/` 目录内。命令行当前内置的下载与基准实现使用 GLM-4V-9B 作为默认样例；这不是项目架构对模型提供方或模型名称的限制。新增或替换模型时，应保持 ModelProvider 接口、项目内模型目录和本地加载约束不变。

使用内置样例时，先以明确 revision 验证小型元数据：

```powershell
max-agent validate-model --model-id ZhipuAI/glm-4v-9b --revision <resolved-revision> --model-dir model\ZhipuAI\glm-4v-9b
max-agent download-model
```

完成下载后，可运行离线单图基准：

```powershell
max-agent --artifact-root artifacts benchmark --model-dir <local-model-dir> --image <local-image-path> --prompt "Describe this image."
```

基准以仅本地文件语义加载模型与分词器；缺少文件时应修复本地模型目录，不允许以隐式联网下载代替。

## 证据归档与安全约束

每次诊断或基准在 `artifacts/` 下创建运行目录，至少包含：

- `config.yaml`：本次命令配置快照；
- `environment.json`：Python、依赖、CUDA 与 BF16 环境信息；
- `trajectory.jsonl`：步骤级事件轨迹；
- `result.json`：成功指标或结构化失败原因。

`model/`、`artifacts/`、模型权重、截图、令牌、密钥和本地缓存均不得提交到 Git。系统测试仅限授权的测试账户、模拟应用或专用测试窗口；未来的桌面控制能力必须显式启用，并经过 Safety Guard、窗口范围、坐标边界、会话锁和急停机制保护。

## 常见问题

| 问题 | 排查方式 |
| --- | --- |
| CUDA 或 BF16 诊断失败 | 检查 GPU 驱动、所安装的 PyTorch 构建与运行时是否匹配，并查看 `max-agent diagnose` 的失败字段。 |
| `pip check` 报冲突 | 在隔离环境中按固定依赖清单重新安装；不要混用 CPU PyTorch 与 CUDA wheel。 |
| 模型目录不完整 | 确认模型位于 `model/` 树内、revision 明确且下载完整；内置 GLM 样例的固定目录为 `model\ZhipuAI\glm-4v-9b`。 |
| 离线基准试图访问网络或无法加载 | 检查本地模型文件和 `--model-dir` 参数；基准只应使用本地文件。 |
| 截图、OCR 或桌面交互无法在自动化终端复现 | 在具有图形桌面权限的交互式会话和受控测试窗口中运行；非交互会话不能替代真实桌面会话。 |
