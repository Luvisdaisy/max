"""基线批次汇总 JSON 的离线 Matplotlib 对比报告。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt


def write_comparison_report(inputs: list[Path], output_root: Path) -> Path:
    """读取 1–5 份 `summary.json`，生成汇总、Markdown 与两张可复核图表。

    参数：`inputs` 为用户指定的基线汇总文件；`output_root` 为报告根目录。
    返回：新建的不可覆盖报告目录。
    异常：输入数量、JSON 结构或文件不可用时抛出 `ValueError`。
    """
    if not 1 <= len(inputs) <= 5:
        raise ValueError("-report 必须提供 1 至 5 份 summary.json")
    records = [_load_summary(path) for path in inputs]
    directory = output_root / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6])
    directory.mkdir(parents=True, exist_ok=False)
    payload = {"inputs": [str(path.resolve()) for path in inputs], "records": records}
    (directory / "comparison.json").write_text(_dump(payload), encoding="utf-8")
    _success_chart(records, directory / "success-rate.png")
    _duration_chart(records, directory / "execution-duration.png")
    (directory / "report.md").write_text(_markdown(records), encoding="utf-8")
    return directory


def _load_summary(path: Path) -> dict[str, object]:
    """读取并验证最小基线汇总字段，拒绝非基线或损坏 JSON。"""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取基线汇总：{path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"不是有效的基线运行记录：{path}")
    if isinstance(value.get("summary"), dict):
        return value["summary"]
    if isinstance(value.get("results"), list):
        return value
    raise ValueError(f"不是有效的基线运行记录：{path}")


def _success_chart(records: list[dict[str, object]], target: Path) -> None:
    """输出按输入批次比较的成功率柱图，并明确显示样本数。"""
    labels = [f"批次 {index}" for index in range(1, len(records) + 1)]
    values = [record.get("success_rate") for record in records]
    numeric = [float(value) if isinstance(value, (int, float)) else 0.0 for value in values]
    fig, axis = plt.subplots(figsize=(7, 4))
    bars = axis.bar(labels, numeric, color="#2f6b9a")
    axis.set_ylim(0, 1)
    axis.set_ylabel("成功率")
    axis.set_title("基线批次成功率")
    for bar, record, value in zip(bars, records, values, strict=True):
        sample = record.get("measured_tasks", 0)
        label = "未知" if value is None else f"{float(value):.1%}"
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.02,
            f"{label}\nn={sample}",
            ha="center",
        )
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _duration_chart(records: list[dict[str, object]], target: Path) -> None:
    """输出按输入批次比较的已知平均执行时长柱图。"""
    labels = [f"批次 {index}" for index in range(1, len(records) + 1)]
    values = [_average_duration(record) for record in records]
    fig, axis = plt.subplots(figsize=(7, 4))
    bars = axis.bar(labels, [value or 0.0 for value in values], color="#c98b3c")
    axis.set_ylabel("平均执行时长（毫秒）")
    axis.set_title("基线批次平均执行时长")
    for bar, value in zip(bars, values, strict=True):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            "未知" if value is None else f"{value:.0f}",
            ha="center",
            va="bottom",
        )
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _average_duration(record: dict[str, object]) -> float | None:
    """仅用逐题记录中已知执行时长计算均值，未知值不按零处理。"""
    values = [
        item.get("execution_duration_ms")
        for item in record["results"]
        if isinstance(item, dict) and isinstance(item.get("execution_duration_ms"), int)
    ]
    return sum(values) / len(values) if values else None


def _markdown(records: list[dict[str, object]]) -> str:
    """生成与 PNG 对应的简短中文报告。"""
    lines = [
        "# 基线 JSON 对比报告",
        "",
        "| 批次 | 样本数 | 成功率 | 平均执行毫秒 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for index, record in enumerate(records, start=1):
        rate = record.get("success_rate")
        rate_text = "未知" if rate is None else f"{float(rate):.1%}"
        duration = _average_duration(record)
        duration_text = "未知" if duration is None else f"{duration:.0f}"
        lines.append(
            f"| 批次 {index} | {record.get('measured_tasks', 0)} | {rate_text} | {duration_text} |"
        )
    return "\n".join(lines) + "\n"


def _dump(value: object) -> str:
    """生成 UTF-8、带结尾换行的 JSON。"""
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"
