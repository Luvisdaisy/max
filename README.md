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

## Doctor

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
