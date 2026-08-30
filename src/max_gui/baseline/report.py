"""基线评测结果、汇总与离线 HTML/SVG 可视化。"""

from __future__ import annotations

import html
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from max_gui.baseline.models import BaselineResult, BaselineStatus


def write_batch(
    directory: Path,
    manifest: dict[str, Any],
    results: list[BaselineResult],
) -> None:
    """写入 manifest、逐题证据、JSON/Markdown 汇总和离线 dashboard。"""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "manifest.json").write_text(_dump(manifest), encoding="utf-8")
    for item in results:
        task_dir = directory / "runs" / item.round_id / item.task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "result.json").write_text(_dump(item.to_dict()), encoding="utf-8")
    summary = summarize(results)
    (directory / "summary.json").write_text(_dump(summary), encoding="utf-8")
    (directory / "summary.md").write_text(_markdown(summary), encoding="utf-8")
    (directory / "dashboard.html").write_text(_dashboard(summary), encoding="utf-8")


def write_run_record(path: Path, manifest: dict[str, Any], results: list[BaselineResult]) -> None:
    """原子写入一份基线运行 JSON，不在基线目录生成分散的逐题文件。"""
    payload = {
        "manifest": manifest,
        "summary": summarize(results),
        "results": [item.to_dict() for item in results],
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(_dump(payload), encoding="utf-8")
    os.replace(temporary, path)


def write_run_report(record: Path, output_root: Path) -> Path:
    """从单份运行 JSON 生成离线 HTML、Markdown 与 SVG 图表报告。"""
    payload = json.loads(record.read_text(encoding="utf-8"))
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("不是有效的基线运行记录")
    directory = output_root / record.stem
    directory.mkdir(parents=True, exist_ok=True)
    from max_gui.baseline.comparison import _duration_chart, _success_chart

    _success_chart([summary], directory / "success-rate.png")
    _duration_chart([summary], directory / "execution-duration.png")
    (directory / "report.md").write_text(_markdown(summary), encoding="utf-8")
    (directory / "dashboard.html").write_text(_dashboard(summary), encoding="utf-8")
    (directory / "source.json").write_text(_dump(payload), encoding="utf-8")
    return directory


def summarize(results: list[BaselineResult]) -> dict[str, Any]:
    """按模型、任务和状态计算保留 null 语义的跨轮聚合。"""
    measured = [item for item in results if item.preflight_status is BaselineStatus.READY]
    known_exec = [item.execution_tokens for item in measured if item.execution_tokens is not None]
    known_review = [item.review_tokens for item in measured if item.review_tokens is not None]
    by_task: dict[str, list[BaselineResult]] = defaultdict(list)
    for item in results:
        by_task[item.task_id].append(item)
    return {
        "tasks": len(results),
        "measured_tasks": len(measured),
        "environment_blocked": sum(
            item.preflight_status is BaselineStatus.ENVIRONMENT_BLOCKED for item in results
        ),
        "safety_blocked": sum(
            item.preflight_status is BaselineStatus.SAFETY_BLOCKED for item in results
        ),
        "success_rate": sum(item.success for item in measured) / len(measured)
        if measured
        else None,
        "known_execution_token_samples": len(known_exec),
        "known_execution_tokens": sum(known_exec) if known_exec else None,
        "known_review_token_samples": len(known_review),
        "known_review_tokens": sum(known_review) if known_review else None,
        "review_errors": sum(item.review_error is not None for item in measured),
        "review_indeterminate": sum(
            str(item.review_verdict) == "indeterminate" for item in measured
        ),
        "review_passes": sum(str(item.review_verdict) == "pass" for item in measured),
        "termination_reasons": dict(Counter(str(item.execution_status) for item in measured)),
        "by_task": {
            name: {
                "n": len(items),
                "success_rate": sum(item.success for item in items) / len(items),
                "average_execution_duration_ms": _mean(
                    [item.execution_duration_ms for item in items]
                ),
                "average_actions": _mean([item.actions for item in items]),
                "review_verdicts": dict(Counter(str(item.review_verdict) for item in items)),
            }
            for name, items in by_task.items()
        },
        "results": [item.to_dict() for item in results],
    }


def _mean(values: list[int | None]) -> float | None:
    """只对已知数值计算均值。"""
    known = [value for value in values if value is not None]
    return sum(known) / len(known) if known else None


def _dump(value: object) -> str:
    """生成带换行的 UTF-8 JSON。"""
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _markdown(summary: dict[str, Any]) -> str:
    """渲染简短、可审计的中文 Markdown 汇总。"""
    return (
        "# 基线桌面评测汇总\n\n"
        f"- 任务记录：{summary['tasks']}\n"
        f"- 模型可测记录：{summary['measured_tasks']}\n"
        f"- 环境阻断：{summary['environment_blocked']}\n"
        f"- 安全阻断：{summary['safety_blocked']}\n"
        f"- 成功率：{summary['success_rate']}\n"
        f"- 已知执行 Token：{summary['known_execution_tokens']}（样本 {summary['known_execution_token_samples']}）\n"
        f"- 已知评审 Token：{summary['known_review_tokens']}（样本 {summary['known_review_token_samples']}）\n"
        f"- 独立评审通过：{summary['review_passes']}；评审不可用：{summary['review_errors']}；"
        f"不可判定：{summary['review_indeterminate']}\n"
    )


def _dashboard(summary: dict[str, Any]) -> str:
    """以标准库生成无网络依赖的 SVG 条形图和明细表。"""
    table_rows: list[str] = []
    bars: list[str] = []
    labels: list[str] = []
    for index, (name, item) in enumerate(summary["by_task"].items()):
        rate = item["success_rate"]
        width = int(rate * 260)
        table_rows.append(
            f"<tr><th>{html.escape(name)}</th><td>{item['n']}</td><td>{rate:.1%}</td>"
            f"<td>{item['average_execution_duration_ms']}</td><td>{item['average_actions']}</td></tr>"
        )
        bars.append(
            f'<rect x="170" y="{35 + 32 * index}" width="{width}" height="18" fill="#21a366"/>'
        )
        labels.append(
            f'<text x="8" y="{49 + 32 * index}" font-size="13">{html.escape(name)}</text>'
        )
    table = "".join(table_rows)
    raw = html.escape(json.dumps(summary, ensure_ascii=False))
    return f"""<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\"><title>基线评测</title>
<style>body{{font-family:-apple-system,sans-serif;margin:32px;color:#172b4d}}table{{border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}svg{{margin:16px 0;background:#f8fafc}}</style>
<h1>基线桌面评测</h1><p>成功率：{summary["success_rate"]}；样本数以各任务 n 为准。未知指标不按零处理。</p>
<svg width=\"460\" height=\"{60 + 32 * len(summary["by_task"])}\">{"".join(labels)}{"".join(bars)}</svg>
<table><thead><tr><th>任务</th><th>n</th><th>成功率</th><th>平均执行毫秒</th><th>平均动作</th></tr></thead><tbody>{table}</tbody></table>
<details><summary>原始汇总 JSON</summary><pre>{raw}</pre></details></html>"""
