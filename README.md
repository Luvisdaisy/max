# MAX 桌面智能体原型

MAX 是面向 Windows 的本地 GUI 智能体原型。当前版本支持本地简单对话和环境诊断；默认不会控制桌面，也不会在诊断证据中记录模型身份信息。

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

## 开始对话与环境诊断

在仓库根目录启动本地会话：

```powershell
max-agent
max-agent --chat
```

普通文本会按需离线加载当前选择的模型并生成回复；启动时默认选择 `model/Qwen/Qwen3.5-2B`。模型不完整、CUDA/BF16 不可用或显存不足时，会话会给出本地修复提示，不会下载模型或回退到网络。

Textual 会话采用键盘优先的终端工作台布局：顶部持续显示当前模型、运行状态与本地只读边界，记录区区分用户、MAX、命令、工具和错误，并以 Markdown 呈现模型回复。编辑区支持 `Enter` 发送、`Shift+Enter` 换行、`Ctrl+Up` / `Ctrl+Down` 浏览本次进程中的输入历史；输入 `/` 会打开可筛选的命令菜单，`Tab` 可补全当前选项。模型推理期间只允许一个活动请求，界面显示当前阶段与已用时间，完成或失败后自动恢复输入焦点。

会话中可使用：

- `/help`：显示全部会话命令和键盘快捷键。
- `/status`：显示当前模型、本地运行时状态和只读安全边界。
- `/model`：列出 `model/` 下包含 `config.json` 的可选模型目录与当前选择。
- `/model <模型目录>`：例如 `/model Qwen/Qwen3.5-4B`；切换后清空当前会话历史，下一条普通消息才加载新模型。
- `/doctor`：执行无输入的环境与基础工具诊断，结果按“通过 / 失败 / 跳过”展示。
- `/clear`：清空可见记录与当前模型的本地对话历史，但保留模型选择和已加载资源。
- `/quit`：安全退出会话。

当普通聊天需要观察当前桌面时，本地模型可以从注册表提供的只读工具中选择一次 `observe_screen`，并在内存中分析截图后回复。界面只显示工具名称、执行状态和耗时，不显示工具参数、原始回执或截图。若模型选择无效工具、参数不符合契约或只读工具执行失败，系统会把仅含工具名、稳定错误分类和安全摘要的失败观察交回模型，让 MAX 理解限制并继续回答原始消息；不会重试或调用第二个工具。只有最终回复生成也失败时，本轮才显示本地运行时错误。该流程不会发送桌面输入、下载模型、访问远程服务或把截图写入日志、结果和归档。需要选择兼容视觉输入且能够在本机显存中加载的模型。

当前会话仍是单进程、单请求的本地原型：尚不支持 token 级流式输出、运行中取消底层推理、请求排队、跨进程会话恢复、完整工具权限系统或 Plan/执行模式。输入历史和聊天记录不会持久化。

诊断会检查 Python、依赖一致性、CUDA、GPU、BF16，以及 mss、PyAutoGUI、OpenCV、PaddleOCR 和 pynput；默认不会发送鼠标或键盘事件。在交互式 Windows 会话中，可显式运行 `max-agent doctor --artifact-root artifacts --desktop-probe`，让短生命周期子进程创建 Win32 原生测试窗口，并仅向其中的 `Edit` 与 `Button` 控件发送受控输入；窗口无法成为前台时不会发送输入。

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
| 本地对话无法启动或生成回复 | 确认 `model/Qwen/Qwen3.5-2B` 模型文件完整、CUDA/BF16 可用，并释放足够的显存后重试。 |
