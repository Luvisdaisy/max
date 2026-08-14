# Windows 11 兼容调研

日期：2026-08-14  
范围：以当前仓库实现（Textual REPL、LangGraph ReAct、OpenAI 兼容 vLLM 客户端、工作区工具、PyAutoGUI 桌面工具）为基准，评估在 Windows 11 上达到「能控本机桌面、能跑通同一套 Agent 闭环」需要改什么。本文只做调研，不改代码。

对照文档：桌面工具调研见 [gui-tools.md](gui-tools.md)；行为以 `openspec/specs/` 为准。第一批桌面规格明确写过「Windows / Linux 一等支持」不在范围内。

## 结论

可以做成 Windows 11 上可用的 GUI Agent，但**不能把整栈原样搬过去**。当前代码是按 Apple Silicon + Metal + macOS 权限模型写的。Agent、TUI、工作区工具大多可移植；真正挡路的是两件事：

1. **桌面控制必须跑在原生 Windows 进程里。** PyAutoGUI 在 WSL2 里点的是 Linux 桌面（WSLg），点不到记事本、资源管理器、微信这类 Win11 窗口。
2. **`max-gui serve` 依赖的独立 vLLM 是 Linux / macOS Metal 路径。** 官方 vLLM 不以原生 Windows 为一等平台。默认二进制是 `~/.venv-vllm-metal/bin/vllm`，启动环境还写死了 macOS 回环口 `lo0`。

推荐部署形态：

| 进程 | 跑在哪 | 原因 |
| --- | --- | --- |
| `max-gui`（TUI + 工具 + PyAutoGUI） | 原生 Windows 11（PowerShell / Windows Terminal） | 必须能截 Win11 屏、点 Win11 窗口 |
| vLLM（主模型，后续 OCR 同理） | WSL2（NVIDIA CUDA）或另一台 Linux / 远程 OpenAI 兼容服务 | 避开原生 Windows 上的 vLLM |
| 二者之间 | 已有 `MAX_GUI_BASE_URL`（默认 `http://127.0.0.1:8000/v1`） | Win11 近年对 WSL2 `localhost` 转发可用 |

不要选「全部放进 WSL2」当一等方案：推理能起，桌面闭环断。也不要在第一期强攻「原生 Windows 编译 vLLM」：投入大、和现有「独立 vLLM 环境、不污染项目 `.venv`」的设计冲突。

落地时应先开 OpenSpec change，再改代码。规格里写死的 macOS 路径、`command+v`、屏幕录制文案都要一并改。

## 兼容目标（建议先钉死）

「Windows 11 兼容」有三种完全不同的验收口径。建议按 **A** 验收，其余当附录。

**A. 原生桌面 Agent（建议）**

- 在 Win11 本机启动 `max-gui`，截主屏、移鼠、点按、拖拽、中英输入，操作的是 Win11 前台窗口。
- 推理可以不在同一个 OS 里，只要 OpenAI 兼容 HTTP 通。
- 单元测试在 `windows-latest` 上能过（假桌面后端，不真动鼠标）。

**B. 仅开发环境可跑**

- TUI、文件工具、会话、连远程模型可用。
- 桌面工具不保证，或只在 100% 缩放的主屏上碰巧能用。

**C. WSL2 全栈**

- `serve` 和 TUI 都在 Linux 子系统里。
- 只能操作 WSLg 里的 Linux GUI，不能当 Win11 桌面 Agent。

本文后续按 **A** 写。若实际目标是 B 或 C，工作量会小一截，但产品语义变了，需要另开 change。

## 现状：哪些已经跨平台

这些模块用的是 `pathlib`、`httpx`、Textual、Pillow，没有绑死 POSIX API，移植成本低。

| 模块 | 判断 |
| --- | --- |
| ReAct 图、工具协议、确认门 | 纯逻辑，与 OS 无关 |
| `InferenceClient` / 图像预处理 | HTTP + Pillow；已支持 `MAX_GUI_BASE_URL` |
| 会话 JSON（`os.replace` 原子写） | Windows 同卷替换可用 |
| 文件读写、搜索 | 显式 `utf-8`；相对路径用 `Path` |
| Textual REPL | 官方支持 Windows；推荐 Windows Terminal |
| `uv` / Python ≥ 3.12 / Ruff | Windows 一等 |
| ModelScope `max-gui download` | 可在 Win11 本机下权重 |
| 测试里的 `FakeDesktopBackend` | 不碰真实键鼠，CI 可复用 |

`pyproject.toml` 没有按平台拆依赖。`pyautogui` 在 Windows 上会拉 `pyscreeze`、`pygetwindow`、`mouseinfo` 等，一般 `uv sync` 就能装上；个别环境还要 `pywin32`。

## 阻塞项（按影响排序）

### 1. 推理：vLLM 不能按现有方式在 Win11 本机拉起

相关代码：[config.py](../src/max_gui/config.py)、[lifecycle.py](../src/max_gui/lifecycle.py)。规格：[multimodal-inference](../openspec/specs/multimodal-inference/spec.md)。

当前约定：

- 查找顺序：`MAX_GUI_VLLM` → `PATH` 里的 `vllm` → `~/.venv-vllm-metal/bin/vllm`
- 禁止回退到项目解释器的 `python -m vllm`
- 错误文案教用户 `source ~/.venv-vllm-metal/bin/activate`
- `serve_model` 无条件设置 `GLOO_SOCKET_IFNAME=lo0`（macOS 回环名；Linux 是 `lo`，Windows 没有这个接口）
- 进行中的 OCR change 复用同一套二进制与 Metal 环境假设

Windows 上会直接碰到：

- 默认路径是 POSIX `bin/vllm`，不是 `Scripts\vllm.exe`
- `os.access(..., os.X_OK)` 对无扩展名脚本、`.cmd` 包装器行为与 Unix 不同
- 即使用户装了 CUDA，官方 vLLM 仍以 Linux 为主；Metal 插件在 Win11 上无意义
- 连接失败文案只说「请先运行 `max-gui serve`」，没有「也可以指到 WSL / 远程」

建议：

- **第一期不把原生 Windows vLLM 当目标。** TUI 在 Win11，推理在 WSL2 或远程。Win11 23H2+ 访问 `http://127.0.0.1:8000` 通常能打到 WSL 里的服务。
- `DEFAULT_VLLM_BIN` 按平台分候选：Windows 可试 `%USERPROFILE%\.venv-vllm\Scripts\vllm.exe`，找不到就只认 `MAX_GUI_VLLM` / `PATH`，文案不要再提 `source` 和 Metal。
- `GLOO_SOCKET_IFNAME` 仅在 macOS 设 `lo0`；Windows / Linux 不设或按平台设。
- `os.access(X_OK)` 改为「存在且 `shutil.which` 能解析」，或接受 `.exe` / `.cmd`。
- `ConnectionFailedError` 补充：设置 `MAX_GUI_BASE_URL` 指向已启动的服务。
- 文档写清 WSL2 安装：CUDA 发行版、在 WSL 里建独立 venv、`vllm serve`、Windows 侧只跑 `max-gui`。

备选（第一期不做）：原生 Windows 推理（llama.cpp、ONNX、厂商 Runtime）。那会换客户端协议或至少换启动器，超过「兼容」范围。

### 2. 桌面：修饰键、粘贴、危险热键全是 macOS 语义

相关代码：[tools/desktop.py](../src/max_gui/tools/desktop.py)、[desktop/pyautogui_backend.py](../src/max_gui/desktop/pyautogui_backend.py)。规格：[desktop-gui-tools](../openspec/specs/desktop-gui-tools/spec.md)。

写死的 macOS 行为：

- 非 ASCII 粘贴：`pyperclip` + **`command+v`**。Win11 上这条热键无效，中文输入会失败。
- 白名单修饰键以 `command` 为主；`cmd` 映射到 `command`。模型按文档会发 `[command, space]`（Spotlight），在 Win11 上应对「开始菜单 / 搜索」，一般是 `win`。
- 危险热键只有 `command+q`、`command+shift+q`、`command+alt+esc`。Win11 真正危险的是 `alt+f4`、`win+l`、`ctrl+alt+del`（后者系统通常拦得住）、`ctrl+shift+esc` 等。
- 权限失败一律说「系统设置 → 隐私与安全性 → 屏幕录制 / 辅助功能」。Win11 没有这两项。
- 工具描述和系统提示词会教模型用 `command`。

建议做成薄的平台表，而不是第二套工具：

| 能力 | macOS | Windows 11 |
| --- | --- | --- |
| 粘贴 | `command+v` | `ctrl+v` |
| 主键名 | `command`（保留 `cmd` 别名） | 接受 `command`/`cmd`/`win`，执行时落到 `win` 或 `ctrl`（见下） |
| 打开搜索 | `command+space` | `win` 或 `win+s` |
| 危险组合 | Cmd-Q 等 | 至少 `alt+f4`、`win+l`、`ctrl+shift+esc`；`ctrl+alt+del` 拒绝即可 |
| 权限文案 | 屏幕录制 + 辅助功能 | 见下一节 |

键名策略（建议选第一种）：

1. **对外仍接受 `command`，按平台翻译。** 模型不用分系统；`command+v` 在 Win11 变成 `ctrl+v`，`command+q` 仍拒绝（或改映射到不执行）。改动面小，和现有测试接近。
2. 工具 schema 改成中性名 `mod` / `meta`，两套别名都收。更干净，但要改描述、测试、已归档规格。

`win` 建议加入命名键白名单，否则模型即使写对了也会被「未知键名」拒掉。

### 3. 桌面：Win11 权限、DPI、UAC 与 macOS 不是同一类问题

macOS 的失败模式是「没授权 → 黑图 / 键鼠没反应」。Win11 常见是另一套：

**截图与键鼠**

- 普通桌面应用一般不需要「屏幕录制」授权，Pillow / `ImageGrab` 就能截主屏。
- 把「全黑或过小」一律解释成缺屏幕录制，在 Win11 上会误导（锁屏、安全桌面、部分全屏游戏、HDR、显卡捕获失败也会黑）。
- Win11 较新版本有截图 / 屏幕录制相关隐私开关；企业策略或杀毒可能拦截 `SendInput`。
- **UAC 安全桌面点不到。** 目标窗口若以管理员运行、Agent 以普通用户运行，键鼠可能无效。这是 Windows 完整性级别，不是辅助功能开关。
- 失败时不要套用 macOS 文案。按平台给出：检查缩放、是否点到 UAC、是否与提权窗口完整性不一致、杀毒是否拦截自动化。

**DPI / 缩放（高概率点偏）**

现有逻辑已经按 Retina 思路算 `scale = 截图像素宽 / pyautogui.size()[0]`，并要求模型用逻辑坐标。Win11 默认 125% / 150% 缩放时：

- 进程若未声明 DPI 感知，`GetSystemMetrics` 与真实截图像素会对不齐，`scale` 能部分兜住，但不能覆盖「每监视器 DPI」和混缩放置。
- Python 3.12 嵌入的可执行文件默认感知级别因构建而异。应用启动时应在 Windows 上显式设为 Per-Monitor V2（`SetProcessDpiAwarenessContext`），再去调 PyAutoGUI。
- 手工验收必须覆盖 100%、125%、150% 三档，不能只在 100% 上点计算器。

**多显示器**

规格已限制主屏。Win11 上任务栏、开始菜单、缩放往往因屏而异。第一期继续只保证主屏；坐标原点以 PyAutoGUI 主屏左上为准，并在 `screen_info` 里写明。

**前台焦点**

TUI 抢焦点的问题和 macOS 一样，甚至更常见：Windows Terminal / VS Code 自己就是前台。已有 `delay_ms` 和中文提示够第一期用。不要第一期做「按标题找窗」；若做，Windows 侧是 `EnumWindows` / UI Automation，会超出当前 PyAutoGUI 薄封装。

### 4. 工作区路径：Windows 大小写、盘符、连接点

[tools/paths.py](../src/max_gui/tools/paths.py) 用 `Path.resolve()` + `relative_to`。在 macOS 默认大小写不敏感、API 却按字节比较的文件系统上已经有边角；Win11 上更明显：

- `C:\Work` 与 `c:\work`：`relative_to` 区分大小写，可能把合法路径判成「逃出工作区」。
- `C:/Work/a.txt` 与 `C:\Work\a.txt`：`resolve()` 一般能归一，但要测。
- 目录联接 / 符号链接：`resolve()` 会跟过去，可以从工作区跳到盘符根。
- 旧式 8.3 短名、`\\?\` 前缀、NTFS 备用数据流（`file.txt:stream`）是更深的逃逸面，第一期可只测联接与大小写。

建议：Windows 上用 `os.path.normcase` 后再比前缀，或 `Path.full_match` / 自写 `is_relative_to` 的大小写不敏感版。测试要补 `C:\` 与 `c:\` 混用。

`list_dir` 用 `/` 标目录，只是展示，可保留。

### 5. 子进程默认编码是系统代码页

`run_python` 已删除（`2026-08-14-remove-run-python-tool`），原先 `subprocess.run(..., text=True)` 在 Win11 中文系统上按 **cp936 / GBK** 解码、超时分支按 UTF-8 的乱码问题随工具一并消失。若以后再加子进程执行，应固定 `encoding="utf-8", errors="replace"`，并设 `PYTHONIOENCODING=utf-8`（或 `PYTHONUTF8=1`）。

### 6. TUI 终端与快捷键

Textual 在 Windows 上可用，但体验依赖终端：

| 终端 | 预期 |
| --- | --- |
| Windows Terminal | 首选；真彩色、Unicode、ConPTY 正常 |
| VS Code 集成终端 | 可用；焦点更容易抢回编辑器 |
| PowerShell 7 挂在旧控制台主机上 | 可能掉色、中文宽字符错位 |
| `cmd.exe` | 不作为支持面 |

`Shift+Enter` 换行依赖终端把组合键完整交给应用；部分主机或远程会话会吞掉。`ctrl+c` 绑定可保留。文档应写「请用 Windows Terminal」，不要承诺 `cmd`。

### 7. 测试与工具链

- [tests/test_cli.py](../tests/test_cli.py) 写 `#!/bin/sh` 再 `chmod 0o755`，再靠 `os.access(X_OK)` 当「可执行」。在 NTFS 上 `chmod` 往往是空操作，测试可能红。
- 断言文案含 `source ~/.venv-vllm-metal`，Windows 适配后必须改成分平台或改成中性提示。
- 危险热键测试只覆盖 `command+q`，要补 Windows 黑名单。
- Ruff 强制 LF。仓库应有 `.gitattributes`（`* text=auto eol=lf`），避免贡献者在 `core.autocrlf=true` 下把检出变成 CRLF。
- 目前看不到 Windows CI。要宣称兼容，至少加 `windows-latest` 跑 `pytest`（继续用假后端）。

### 8. 进行中的 OCR

[openspec/changes/add-ocr-tool/](../openspec/changes/add-ocr-tool/) 尚未实现，设计绑定 `~/.venv-vllm-metal` 和第二套 `vllm serve`。Windows 兼容不要和 OCR 绑在同一个 change 里。OCR 落地时：第二服务仍放 WSL / 远程；transformers 回退用「vLLM 同环境的 `python.exe`」，不要灌进项目 `.venv`。

## 建议架构

```text
┌──────────────────────────── Win11 本机 ────────────────────────────┐
│  Windows Terminal                                                  │
│    max-gui (项目 .venv)                                            │
│      Textual / ReAct / 工作区工具                                  │
│      PyAutoGUI → 本机屏幕、鼠标、键盘、剪贴板                       │
│      InferenceClient ──HTTP──► 127.0.0.1:8000                     │
└───────────────────────────────────┬────────────────────────────────┘
                                    │ localhost 转发
┌───────────────────────────────────▼────────────────────────────────┐
│  WSL2（Ubuntu + NVIDIA CUDA）或远程 Linux                          │
│    ~/.venv-vllm/bin/vllm serve model/qwen3.5-2b …                  │
│    权重可放 Windows 盘 bind mount，或 WSL 内再下一份                 │
└────────────────────────────────────────────────────────────────────┘
```

权重很大（2B / 4B / 9B）。优先让 WSL 读 Windows 侧 `model/`（`/mnt/c/...`），避免拷两份；若 I/O 太慢再在 ext4 上放一份。

项目 `.venv` 继续保持「无 torch / 无 vLLM」，这条约束在 Windows 上同样成立。

## 代码改动清单（若开 change）

只列为了 **目标 A** 必须动的地方。不要顺手重构 Agent 图。

1. **平台桌面表**（`desktop/` 或 `tools/desktop.py`）  
   粘贴热键、修饰键别名、危险热键、权限中文说明。`PyAutoGUIBackend.paste` 不要写死 `command`。
2. **启动时 DPI**（仅 `sys.platform == "win32"`）  
   在第一次调用 PyAutoGUI 之前设置 Per-Monitor V2。
3. **权限错误分类**  
   `DesktopPermissionError` 的文案按平台生成；黑图在 Windows 上不要只说「屏幕录制」。
4. **vLLM 发现与 serve 环境**  
   默认路径、可执行判断、`GLOO_SOCKET_IFNAME`、中文错误与 `ConnectionFailedError`。
5. **工作区路径**  
   Windows 下大小写不敏感的包含判断。
6. **规格与用户文案**  
   `desktop-gui-tools`、`multimodal-inference`、README、AGENTS.md：Win11 步骤、推荐终端、推理放 WSL / 远程。
7. **测试**  
   平台热键与粘贴、路径大小写、vLLM 查找；CI 加 `windows-latest`。

明确第一期不做：按窗口标题切换、UI Automation 控件树、原生 Windows vLLM、多显示器、滚轮、把 TUI 嵌进被控 GUI。

## 手工验收（必须在真机，不能只靠 CI）

环境：Win11 22H2+，Windows Terminal，显示缩放可改，一块主屏即可。推理用 WSL2 或另一台机器上已有的 `vllm serve`。

1. `uv sync --group dev`，`uv run pytest`，`uv run ruff check src tests`。
2. `max-gui download`（若本机无权重）只验证本机写盘；不要求本机 `serve`。
3. 设置 `MAX_GUI_BASE_URL` 后启动 TUI，发一句话，确认流式输出。
4. 计算器闭环：截图 → 点图标 → 输入 `1+1` → 回车 → 再截图读结果。分别在 **100% / 125% / 150%** 缩放下做。
5. 中文：`keyboard_type("你好")` 应出现在记事本，而不是丢掉或打出 `command` 相关乱键。
6. 确认门：点击 / 输入仍要确认；`auto_approve` 不能放行桌面工具。
7. 拒绝 `alt+f4`（以及仍拒绝 `command+q`，若保留翻译策略）。
8. 工作区：用 `C:\...` 与 `c:\...` 读同一文件应成功；`..\..\Windows\System32` 应失败。
9. 负例：不要在 WSL 里跑 `max-gui` 再声称「已支持 Win11 桌面」。

## 建议的落地顺序

1. 用 OpenSpec 开 change（例如 `windows11-compat`），把目标 A、推理外置、键位翻译写进 proposal / design / specs / tasks。
2. 先做键位、粘贴、权限文案、DPI、路径、编码。这些不依赖 Windows 上的 GPU，macOS 开发机也能改完、用测试钉住。
3. 再改 vLLM 发现与文档；在一台有 NVIDIA 的 Win11 + WSL2 上跑通 `BASE_URL`。
4. 加 `windows-latest` CI 与上面的手工清单。
5. 归档 change，同步 README / AGENTS.md。

## 工作量粗估

| 块 | 体量 | 说明 |
| --- | --- | --- |
| 桌面平台表 + 测试 | 小到中 | 行为变化集中，规格要改 |
| DPI + 权限文案 | 小 | 要真机验证 |
| 路径 / 编码 / vLLM 查找 | 小 | 纯工程，回归面清楚 |
| WSL2 推理文档与一次联调 | 中 | 不在仓库里编 vLLM，但环境差大 |
| Windows CI | 小 | 假后端即可 |
| 原生 Windows vLLM | 大，且不建议第一期 | 超出兼容 |

整体上，**按目标 A、不做原生 vLLM**，是一个中等体量的 OpenSpec change，不是重写。风险在真机 DPI / UAC / 终端，不在 ReAct 本身。

## 和现有文档的关系

- [gui-tools.md](gui-tools.md) 仍是 macOS 第一批桌面调研；其中「不做 Windows 一等支持」被本文取代为「下一阶段要做，且必须原生进程控桌面」。
- 实现前以新 change 的 specs 为准；本文不是规格。
- OCR change 不要搭车改 Windows；等桌面与推理部署约定稳定后再让 OCR 跟同一套「推理外置」模型。
