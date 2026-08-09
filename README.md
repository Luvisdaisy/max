# MAX 桌面智能体原型

MAX 是面向 Windows 的本地 GUI 智能体原型。当前第一周交付提供 Doctor 环境与基础工具核验；它不会默认控制桌面，也不会在 Doctor 证据中记录任何模型信息。

交互入口采用 CLI 优先策略：Typer 负责命令入口，Rich 负责终端输出，Prompt Toolkit 负责默认交互式会话。Textual 保留为后续可选的高级 UI，不是基础 CLI 运行的必要依赖。

## 使用环境

项目支持 Windows 11 与 Python `>=3.12,<3.13`。可以使用 venv、uv 或 Conda 创建隔离环境；三种方式都从仓库根目录的同一个 `requirements.txt` 安装项目及全部 Python 依赖。GPU 相关核验要求 NVIDIA CUDA 运行时和 BF16 张量运算支持。

### venv + pip

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip check
```

### uv

```powershell
uv venv --python 3.12
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
python -m pip check
```

### Conda + pip

```powershell
conda create -n max python=3.12 -y
conda activate max
python -m pip install -r requirements.txt
python -m pip check
```

以上安装命令必须在仓库根目录执行。`requirements.txt` 已包含 CUDA 13.0 PyTorch wheel 索引、应用依赖、桌面/UIA/OCR 依赖和 `-e .`，因此无需再组合其他 requirements 文件或单独执行 editable 安装。Conda 环境名称可以自行调整，不要求必须命名为 `max`。

## 代码质量与 CI

提交前在仓库根目录执行以下质量门禁；检查命令不会下载或加载 `model/` 中的模型，也不会发出桌面控制输入。

```powershell
ruff format --check src tests
ruff check src tests
python -m unittest discover -s tests -v
python -m pip check
```

需要修复本地工作区时，开发者可主动运行 `ruff format src tests` 与 `ruff check --fix src tests`，随后再次执行上述检查。GitHub Actions 会在 `push` 和 `pull_request` 的 Windows / Python 3.12 环境按相同顺序执行这些门禁；CI 不启动 `max-agent`，也不执行模型下载、基准或桌面控制。

## Doctor

## Textual 聊天入口（破坏性变更）

当前版本仅支持以下启动形式，两者都会打开同一个 Textual 本地聊天界面：

```powershell
max-agent
max-agent --chat
```

普通文本会按需离线加载 `model/Qwen/Qwen3.5-2B`；模型不完整、CUDA/BF16 不可用或显存不足时，界面会显示本地修复提示，不会下载模型或回退到网络。运行中的 `/doctor` 会执行无输入诊断，`/quit` 退出会话。`doctor`、`download-model`、`validate-model`、`benchmark`、`--doctor`、`--fallback` 和 `--textual` 不再是公开 CLI 操作；相关实现仅保留给未来内部 API 或后续入口使用。

以下早期 Doctor 命令示例已废弃，应使用 Textual 会话中的 `/doctor`。

在仓库根目录运行：

```powershell
max-agent --artifact-root artifacts doctor
```

Doctor 会以“通过 / 失败 / 跳过”分组展示 Python、依赖一致性、CUDA、GPU、BF16，以及 mss、PyAutoGUI、OpenCV、PaddleOCR 和 pynput 的无输入检查。运行记录存于 Git 忽略的 `artifacts/`，其中不包含模型型号、模型目录、远程修订或文件集合身份。

默认交互控制台使用 Prompt Toolkit，可使用 `/doctor`，使用 `/quit` 退出：

```powershell
max-agent
```

也可以显式启动同一 CLI 交互路径：

```powershell
max-agent --chat
```

`--fallback` 仍作为兼容别名保留。后续如需体验 Textual 高级界面，可显式运行：

```powershell
max-agent --textual
```

默认 Doctor 不会发送鼠标或键盘事件。仅在已授权的交互式 Windows 会话中，才可显式运行受控测试窗口探针：

```powershell
max-agent --artifact-root artifacts doctor --desktop-probe
```

该探针只对临时测试窗口验证前台句柄、点击和文本输入；同一次 Doctor 还会检查内存截图和 PaddleOCR 包可用性，但不会执行可能隐式下载资源的完整 OCR 识别。窗口不可用、焦点丢失或坐标不匹配时应停止并报告失败。

## 证据与安全边界

每次 Doctor 运行会在 `artifacts/` 下创建目录，并写入：

- `config.yaml`：命令配置；
- `environment.json`：运行时和工具检查结果；
- `trajectory.jsonl`：步骤事件；
- `result.json`：最终状态与失败原因。

`artifacts/`、截图、令牌、密钥和本地缓存均不得提交到 Git。桌面输入测试仅限授权的测试账户、模拟应用或专用测试窗口。

## 常见问题

| 问题 | 排查方式 |
| --- | --- |
| CUDA 或 BF16 检查失败 | 确认已激活完成依赖安装的 Python 环境，并检查驱动与 PyTorch CUDA 构建是否匹配。 |
| 基础工具检查失败 | 查看 Doctor 的失败条目；在交互式 Windows 会话中复核显示器与桌面权限。 |
| `pip check` 报冲突 | 在隔离环境中按项目依赖清单重新安装。 |
| 显式桌面探针失败 | 关闭其他会抢占焦点的窗口，再在受控测试桌面中重试；不要在真实业务应用中运行。 |

## 本地离线 4B 基准

基准只支持已显式下载到仓库 `model/Qwen/Qwen3.5-4B` 的 Qwen3.5-4B。首次下载需要网络，随后基准严格使用本地文件；不会下载缺失的模型文件或回退到远程资源。

```powershell
max-agent download-model
max-agent benchmark --model-dir model/Qwen/Qwen3.5-4B --image tests/fixtures/one-pixel.ppm --artifact-root artifacts
```

运行前会验证固定模型目录、模型配置与全部权重分片，以及 `--image` 指定图像能否解码。完成或在归档创建后失败时，都会在 `artifacts/<timestamp>-benchmark/` 写入 `config.yaml`、`environment.json`、`trajectory.jsonl` 与 `result.json`。证据记录包含离线状态、参数、加载时间、峰值显存、推理延迟和结果阶段，但不包含模型权重、图像内容或绝对本地路径。

真实运行需要已完成下载、可用 CUDA/BF16 环境和足够显存；自动化测试不会执行模型推理。可先检查 `result.json` 的 `status`、`stage` 和计时字段，再将产物保留在 Git 忽略的 `artifacts/` 中。

2026-08-09 的实际验收使用上述夹具和 `--max-new-tokens 8`，预检通过但在加载阶段因显存不足而失败：16 GiB 显卡当时约有 7.46 GiB 空闲，加载还需要额外 40 MiB。再次运行前关闭其他 CUDA 进程，确认有足够可用显存后，重复同一条命令；不要将本次失败当作模型推理成功。
