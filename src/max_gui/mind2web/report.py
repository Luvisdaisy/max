"""Online-Mind2Web 的任务级和批次级可审计报告。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from max_gui.mind2web.models import EvaluationSummary


def write_reports(
    output_dir: Path, manifest: dict[str, Any], summary: EvaluationSummary
) -> tuple[Path, Path]:
    """写入不含凭据的 JSON 和 Markdown 汇总。

    参数：`output_dir` 是独立评测目录，`manifest` 是冻结运行元数据，`summary` 是任务结果。
    返回：JSON 与 Markdown 文件路径。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = summary.to_dict()
    json_path = output_dir / "summary.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = output_dir / "summary.md"
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    return json_path, markdown_path


def _markdown(payload: dict[str, Any]) -> str:
    """把稳定汇总字段渲染为便于人工审计的中文 Markdown。"""
    rows = [
        ("计划任务", payload["planned_tasks"]),
        ("预检 ready", payload["ready_tasks"]),
        ("实际执行", payload["executed_tasks"]),
        ("环境不可执行", payload["environment_unexecutable_tasks"]),
        ("安全阻断", payload["safety_blocked_tasks"]),
        ("模型未完成", payload["model_incomplete_tasks"]),
        ("有效轨迹", payload["trajectory_valid_tasks"]),
        ("Judge 待执行", payload["judge_pending_tasks"]),
        ("Judge 错误", payload["judge_error_tasks"]),
        ("WebJudge 已判", payload["webjudge_evaluated_tasks"]),
        ("模型完成率", payload["model_completion_rate"]),
        ("模型任务成功率", payload["model_task_success_rate"]),
        ("端到端成功率", payload["end_to_end_success_rate"]),
        ("已知 Token 样本", payload["known_token_samples"]),
        ("已知 Token 总量", payload["total_tokens"]),
        ("平均动作效率", payload["average_action_efficiency"]),
    ]
    return (
        "# Online-Mind2Web 评测汇总\n\n| 指标 | 值 |\n| --- | --- |\n"
        + "\n".join(f"| {name} | {value} |" for name, value in rows)
        + "\n\n环境/安全状态不进入模型完成率分母；未判分时端到端成功率为 null；未知 Token 不按零统计。\n"
    )
