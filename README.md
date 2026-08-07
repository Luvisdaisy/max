# MAX 桌面智能体原型

MAX 是面向 Windows 的本地 GUI 智能体原型。当前第一周交付提供 Doctor 环境与基础工具核验；它不会默认控制桌面，也不会在 Doctor 证据中记录任何模型信息。

## 使用环境

项目使用 Conda `max` 环境与 Python 3.12。GPU 相关核验要求 NVIDIA CUDA 运行时和 BF16 张量运算支持。

```powershell
conda activate max
python -m pip install -e .
python -m pip check
```

## Doctor

在仓库根目录运行：

```powershell
max-agent --artifact-root artifacts doctor
```

Doctor 会以“通过 / 失败 / 跳过”分组展示 Python、依赖一致性、CUDA、GPU、BF16，以及 mss、PyAutoGUI、OpenCV、PaddleOCR 和 pynput 的无输入检查。运行记录存于 Git 忽略的 `artifacts/`，其中不包含模型型号、模型目录、远程修订或文件集合身份。

聊天控制台中可使用 `/doctor`，使用 `/quit` 退出：

```powershell
max-agent --chat
```

默认 Doctor 不会发送鼠标或键盘事件。仅在已授权的交互式 Windows 会话中，才可显式运行受控测试窗口探针：

```powershell
max-agent --artifact-root artifacts doctor --desktop-probe
```

该探针只对临时测试窗口验证截图、OCR 样例、点击和文本输入；窗口不可用、焦点丢失或坐标不匹配时应停止并报告失败。

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
| CUDA 或 BF16 检查失败 | 确认已激活 `max` 环境，并检查驱动与 PyTorch CUDA 构建是否匹配。 |
| 基础工具检查失败 | 查看 Doctor 的失败条目；在交互式 Windows 会话中复核显示器与桌面权限。 |
| `pip check` 报冲突 | 在隔离环境中按项目依赖清单重新安装。 |
| 显式桌面探针失败 | 关闭其他会抢占焦点的窗口，再在受控测试桌面中重试；不要在真实业务应用中运行。 |
