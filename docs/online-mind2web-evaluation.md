# Online-Mind2Web 评测使用说明

此能力与 `--benchmark` 的本地可重置评测完全独立。它只接受你已取得并有权使用的任务 JSON，不会下载数据、
接受数据集条款、使用个人账号或绕过登录/CAPTCHA。

## 前置条件

准备任务文件和安全清单，并把它们放在项目工作区内。任务 JSON 可以是数组，或含 `tasks` 数组的对象；每题必须有
`task_id`、`website`、`task_description`（或 `instruction`）和正整数 `reference_length`。任务 ID 不能重复。

安全清单示例：

```json
{
  "name": "first-readonly-smoke",
  "rules": [
    {
      "task_id": "你的 task id",
      "allowed_domains": ["example.com"],
      "max_steps": 12,
      "timeout_seconds": 120,
      "allowed_type_values": ["允许输入的非敏感文本"]
    }
  ]
}
```

首批清单只应包含无登录、无上传、无购买/预约/发布/提交的只读任务。未列入清单、跳出允许域、登录/CAPTCHA、
敏感输入和高后果动作会被分类为环境或安全结果，不应算作模型失败。

## 命令与结果

先只生成本地预检，不会启动浏览器：

```bash
uv run max-gui online-mind2web --tasks path/to/tasks.json --safety path/to/safety.json
```

人工确认首批任务后，才显式加入 `--run`：

```bash
uv run max-gui online-mind2web --tasks path/to/tasks.json --safety path/to/safety.json --run
```

每题使用新的临时 Chrome profile，固定窗口、英文界面和缩放，并只在 `127.0.0.1` 开启调试端口。URL 观察器只读当前
tab URL，不向 Agent 提供 DOM、CDP 或网页脚本能力。每个批次输出在
`artifacts/evaluations/online-mind2web/<run-id>/`，其中包含任务/清单摘要、预检结果、逐题 `result.json`、截图及
JSON/Markdown 汇总；目录不写回上游 `artifacts/Online-Mind2Web` 克隆。

任务只有成功执行 `task_complete`、获得独立后置截图、URL 可观察并通过本地 v2 校验后，才会生成可提交的
`result.json`。模型自然停止、超时、站点拦截或安全阻断不会被记为完成。截图、OCR 与 hover 不消耗
交互动作预算；当前评测默认不暴露控件定位工具，模型应根据最新截图使用视图像素，点击、滚动、键盘和完成声明才消耗预算。

## WebJudge 与人工抽检

WebJudge 仅在本地 v2 验证通过后，且明确指定 `--judge` 时调用，默认单 worker。例如：

```bash
OPENAI_API_KEY=... uv run max-gui online-mind2web --tasks path/to/tasks.json --safety path/to/safety.json --run --judge --judge-model gpt-4.1
```

也可用 `--judge-api-key-env` 指定不同的凭据变量名。未开启 Judge 时，合法轨迹标为 `judge_pending`，端到端
成功率为 `null`，不是零成功率。凭据应仅通过环境变量提供；不要写入任务、清单、manifest 或
日志。WebJudge 输出需要结合至少一题的截图、URL、动作序列和最终页面状态人工抽检；站点更新、地域差异和自动判分误差
均可能影响结果。真实网站运行具有外部风险，开始前请逐项确认 task id、域名和输入白名单。
