"""从多份基线运行 JSON 原子生成 Markdown 表格与中文柱状图。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager, ft2font
from matplotlib import pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Patch

CHINESE_FONT_CANDIDATES = (
    "PingFang SC",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "WenQuanYi Zen Hei",
    "Hiragino Sans GB",
    "Heiti SC",
    "Arial Unicode MS",
)
PROJECT_CHINESE_FONT = Path(__file__).resolve().parents[3] / "artifacts/fonts/Microsoft YaHei.ttf"
CHINESE_LABELS = (
    "基线模型对比总分成功率平均步长平均执行时长平均总时长工具调用总数工具失败次数执行令牌未知"
)
MODEL_PALETTE = (
    "#4E79A7",
    "#F28E2B",
    "#E15759",
    "#76B7B2",
    "#59A14F",
    "#EDC948",
    "#B07AA1",
    "#FF9DA7",
    "#9C755F",
    "#BAB0AC",
)


@dataclass(frozen=True, slots=True)
class _ReportRow:
    """一份运行记录在表格和所有图表中的统一指标行。"""

    model: str
    source: Path
    overall_score: float | None
    success_rate: float | None
    average_actions: float | None
    average_execution_duration_ms: float | None
    average_total_duration_ms: float | None
    total_tool_calls: float | None
    total_tool_failures: float | None
    execution_tokens: float | None


@dataclass(frozen=True, slots=True)
class _Metric:
    """一列报告指标及其柱状图展示配置。"""

    attribute: str
    header: str
    title: str
    ylabel: str
    filename: str
    format_kind: str


METRICS = (
    _Metric("overall_score", "总分", "模型总分对比", "总分", "overall-score.png", "score"),
    _Metric("success_rate", "成功率", "模型成功率对比", "成功率", "success-rate.png", "rate"),
    _Metric(
        "average_actions", "平均步长", "模型平均步长对比", "步", "average-actions.png", "decimal"
    ),
    _Metric(
        "average_execution_duration_ms",
        "平均执行时长（毫秒）",
        "模型平均执行时长对比",
        "毫秒",
        "average-execution-duration.png",
        "integer",
    ),
    _Metric(
        "average_total_duration_ms",
        "平均总时长（毫秒）",
        "模型平均总时长对比",
        "毫秒",
        "average-total-duration.png",
        "integer",
    ),
    _Metric(
        "total_tool_calls",
        "工具调用总数",
        "模型工具调用总数对比",
        "次",
        "total-tool-calls.png",
        "integer",
    ),
    _Metric(
        "total_tool_failures",
        "工具失败次数",
        "模型工具失败次数对比",
        "次",
        "total-tool-failures.png",
        "integer",
    ),
    _Metric(
        "execution_tokens",
        "执行 Token 总数",
        "模型执行 Token 总数对比",
        "Token",
        "execution-tokens.png",
        "integer",
    ),
)


def write_comparison_report(inputs: list[Path], output_root: Path) -> Path:
    """读取 1–5 份运行 JSON，原子生成 Markdown 与八张模型对比图。

    参数：`inputs` 按用户指定顺序排列；`output_root` 是报告根目录。
    返回：新建且不会覆盖旧报告的目录。
    异常：数量非法、输入不可读、结构损坏或无可用中文字体时抛出 `ValueError`。
    """
    if not 1 <= len(inputs) <= 5:
        raise ValueError("-report 必须提供 1 至 5 份基线运行 JSON")
    rows = [_load_row(path) for path in inputs]
    font = _select_chinese_font()
    colors = _model_colors([row.model for row in rows])
    output_root.mkdir(parents=True, exist_ok=True)
    final = output_root / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6])
    temporary = Path(tempfile.mkdtemp(prefix=".baseline-report-", dir=output_root))
    try:
        charts = temporary / "charts"
        charts.mkdir()
        for metric in METRICS:
            _write_chart(rows, metric, colors, font, charts / metric.filename)
        (temporary / "report.md").write_text(_markdown(rows), encoding="utf-8")
        os.replace(temporary, final)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return final


def _load_row(path: Path) -> _ReportRow:
    """从当前运行 JSON 提取一行报告指标，不承担评分计算。"""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = payload["manifest"]
        summary = payload["summary"]
        return _ReportRow(
            model=str(manifest["model"]),
            source=path.resolve(),
            overall_score=_number(summary["overall_score"]),
            success_rate=_number(summary["success_rate"]),
            average_actions=_number(summary["average_actions"]),
            average_execution_duration_ms=_number(summary["average_execution_duration_ms"]),
            average_total_duration_ms=_number(summary["average_total_duration_ms"]),
            total_tool_calls=_number(summary["total_tool_calls"]),
            total_tool_failures=_number(summary["total_tool_failures"]),
            execution_tokens=_number(summary["known_execution_tokens"]),
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"无法读取基线运行记录：{path}") from exc


def _number(value: object) -> float | None:
    """把 JSON 数值规范为浮点数，并保留空值。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("报告指标必须是数值或 null")
    return float(value)


def _select_chinese_font() -> FontProperties:
    """优先选择项目微软雅黑，再按跨平台候选顺序检查系统字体。"""
    if _font_supports_labels(PROJECT_CHINESE_FONT):
        return FontProperties(fname=PROJECT_CHINESE_FONT)
    entries = font_manager.fontManager.ttflist
    for candidate in CHINESE_FONT_CANDIDATES:
        for entry in entries:
            if entry.name.casefold() != candidate.casefold():
                continue
            if _font_supports_labels(Path(entry.fname)):
                return FontProperties(fname=entry.fname)
    names = "、".join(CHINESE_FONT_CANDIDATES)
    raise ValueError(f"无法生成中文图表：请安装以下任一字体：{names}")


def _font_supports_labels(path: Path) -> bool:
    """验证字体文件存在且覆盖报告使用的全部中文标签字形。"""
    if not path.is_file():
        return False
    try:
        character_map = ft2font.FT2Font(path).get_charmap()
    except (OSError, RuntimeError):
        return False
    required = {ord(character) for character in CHINESE_LABELS}
    return required.issubset(character_map)


def _model_colors(models: list[str]) -> dict[str, str]:
    """为不同模型生成稳定且互不冲突的调色板映射。"""
    assigned: dict[str, str] = {}
    used: set[str] = set()
    for model in sorted(set(models)):
        digest = hashlib.sha256(model.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % len(MODEL_PALETTE)
        for offset in range(len(MODEL_PALETTE)):
            color = MODEL_PALETTE[(index + offset) % len(MODEL_PALETTE)]
            if color not in used:
                assigned[model] = color
                used.add(color)
                break
    return assigned


def _write_chart(
    rows: list[_ReportRow],
    metric: _Metric,
    colors: dict[str, str],
    font: FontProperties,
    target: Path,
) -> None:
    """生成单指标多模型柱状图，并把缺失字形 warning 视为失败。"""
    values = [getattr(row, metric.attribute) for row in rows]
    positions = list(range(len(rows)))
    with warnings.catch_warnings(), matplotlib.rc_context({"axes.unicode_minus": False}):
        warnings.filterwarnings("error", message=r"Glyph .* missing from font.*")
        figure, axis = plt.subplots(figsize=(max(7, len(rows) * 1.4), 4.5))
        try:
            bars = axis.bar(
                positions,
                [value if value is not None else 0.0 for value in values],
                color=[colors[row.model] for row in rows],
            )
            axis.set_xticks(positions, [row.model for row in rows], fontproperties=font)
            axis.set_ylabel(metric.ylabel, fontproperties=font)
            axis.set_title(metric.title, fontproperties=font)
            for bar, value in zip(bars, values, strict=True):
                axis.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height(),
                    _format_value(value, metric.format_kind),
                    ha="center",
                    va="bottom",
                    fontproperties=font,
                )
            handles = [
                Patch(facecolor=colors[model], label=model)
                for model in dict.fromkeys(row.model for row in rows)
            ]
            axis.legend(handles=handles, prop=font)
            figure.tight_layout()
            figure.savefig(target, dpi=160)
        finally:
            plt.close(figure)


def _markdown(rows: list[_ReportRow]) -> str:
    """生成模型名行头、固定指标列和相对图表引用的 Markdown。"""
    headers = ["模型", *(metric.header for metric in METRICS)]
    lines = [
        "# 基线模型对比报告",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---", *("---:" for _ in METRICS)]) + " |",
    ]
    for row in rows:
        values = [
            _format_value(getattr(row, metric.attribute), metric.format_kind) for metric in METRICS
        ]
        lines.append("| " + " | ".join([_escape_cell(row.model), *values]) + " |")
    lines.extend(["", "## 指标对比图", ""])
    for metric in METRICS:
        lines.extend(
            [f"### {metric.header}", "", f"![{metric.title}](charts/{metric.filename})", ""]
        )
    lines.extend(["## 输入记录", ""])
    for index, row in enumerate(rows, start=1):
        lines.append(f"{index}. `{row.model}`：`{row.source}`")
    return "\n".join(lines) + "\n"


def _format_value(value: float | None, kind: str) -> str:
    """按表格列语义格式化数值或中文未知标记。"""
    if value is None:
        return "未知"
    if kind == "rate":
        return f"{value:.1%}"
    if kind == "score":
        return f"{value:.2f}"
    if kind == "decimal":
        return f"{value:.2f}"
    return f"{value:.0f}"


def _escape_cell(value: str) -> str:
    """转义 Markdown 表格中会破坏列结构的模型名字符。"""
    return value.replace("|", "\\|").replace("\n", " ")
