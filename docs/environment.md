# 第一周环境与复现指南

目标机器：Windows 11、Conda `max`、Python 3.12.13、RTX 5070 Ti 与 CUDA 13.0 PyTorch。

## 安装

```powershell
conda activate max
python -m pip install --index-url https://download.pytorch.org/whl/cu130 -r requirements/torch-cu130.txt
python -m pip install -r requirements/base.txt
python -m pip install -e .
```

依赖版本见 `requirements/constraints.txt`。CUDA PyTorch 必须从官方 cu130 索引安装；其余包使用常规 PyPI。安装后运行 `pip check` 与真实 BF16 CUDA 计算自检。

## 诊断

```powershell
max-agent --artifact-root artifacts diagnose
```

诊断将记录 Python、包版本、CUDA、BF16 和 `pip check` 结果。失败会返回非零状态，且不会加载模型、启动服务或控制桌面。

## 模型与产物位置

- 模型缓存：项目内 Git-ignored 的 `F:\Coding\max\model`。
- 实验记录：仓库内被忽略的 `artifacts/`。
- 模型权重、真实截图、个人数据、令牌、Paddle/COM 自动生成代码均不得提交。

先验证一个小的 `config.json`：

```powershell
max-agent validate-model --model-id ZhipuAI/glm-4v-9b --revision <RESOLVED_REVISION> --model-dir model\ZhipuAI\glm-4v-9b
```

然后在明确模型 revision 后才执行完整下载：

```powershell
modelscope download --model ZhipuAI/glm-4v-9b --local_dir F:\Coding\max\model\ZhipuAI\glm-4v-9b
```

目前不会执行完整下载，因为最终 revision 与基准图许可证尚未确认。
