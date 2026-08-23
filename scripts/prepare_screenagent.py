"""把 ScreenAgent 原始 session 转成统一 JSONL，供规划 few-shot 与第五周 LoRA 使用。

运行：``uv run python scripts/prepare_screenagent.py``

默认读取 ``artifacts/datasets/screenagent/{train,test}``，写出
``artifacts/datasets/screenagent/processed/``。不启动浏览器、VNC 或模型。

动作映射（改映射先改 [docs/gui-datasets-week3.md](docs/gui-datasets-week3.md)）：

- ``MouseAction.click`` / ``double_click`` → ``mouse_click``
- ``MouseAction.move`` → ``mouse_move``
- ``MouseAction.drag`` 以及同一步里的 ``down``+``up`` → ``mouse_drag``
- ``MouseAction.scroll_up`` / ``scroll_down`` → ``mouse_scroll``
- ``KeyboardAction.text`` → ``keyboard_type``
- ``KeyboardAction.press`` → ``keyboard_press``
- ``PlanAction`` / ``EvaluateSubTaskAction`` 不调工具
- ``WaitAction`` 与无法映射的键名记入统计后丢弃该条动作

坐标保持 1024×768 图像像素，不换算到本机逻辑分辨率。
负例 ``*_neg_*.json`` 不进入 JSONL。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW = PROJECT_ROOT / "artifacts" / "datasets" / "screenagent"
DEFAULT_OUT = DEFAULT_RAW / "processed"

# X11 keysym / 数据集别名 → 本仓库 keyboard_press 键名。
KEY_MAP = {
    "return": "enter",
    "kp_enter": "enter",
    "enter": "enter",
    "escape": "esc",
    "esc": "esc",
    "backspace": "backspace",
    "delete": "delete",
    "tab": "tab",
    "space": "space",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "super_l": "command",
    "super_r": "command",
    "super": "command",
    "win": "command",
    "windows": "command",
    "control_l": "ctrl",
    "control_r": "ctrl",
    "control": "ctrl",
    "ctrl": "ctrl",
    "alt_l": "alt",
    "alt_r": "alt",
    "alt": "alt",
    "shift_l": "shift",
    "shift_r": "shift",
    "shift": "shift",
    "command": "command",
    "cmd": "command",
}
NAMED_KEYS = {
    "enter",
    "tab",
    "esc",
    "backspace",
    "space",
    "delete",
    "up",
    "down",
    "left",
    "right",
    "command",
    "shift",
    "ctrl",
    "alt",
}
SUBTASK_RE = re.compile(r"现在的子任务是\s*[\"“](.+?)[\"”]")
SUBTASK_EN_RE = re.compile(r'(?:current subtask|The current subtask) is\s+"([^"]+)"', re.I)

IMAGE_WIDTH = 1024
IMAGE_HEIGHT = 768


class ConvertStats:
    """一次预处理的计数器，最后写成中文报告。"""

    def __init__(self) -> None:
        """初始化所有计数桶。"""
        self.sessions: dict[str, int] = {}
        self.positive_json = 0
        self.skipped_neg = 0
        self.written = 0
        self.skipped: Counter[str] = Counter()
        self.stages: Counter[str] = Counter()
        self.tools: Counter[str] = Counter()
        self.raw_actions: Counter[str] = Counter()
        self.unmapped_actions: Counter[str] = Counter()
        self.unmapped_keys: Counter[str] = Counter()

    def as_dict(self) -> dict[str, Any]:
        """转成可 JSON 序列化的统计。"""
        return {
            "sessions": self.sessions,
            "positive_json": self.positive_json,
            "skipped_neg": self.skipped_neg,
            "written": self.written,
            "skipped": dict(self.skipped),
            "stages": dict(self.stages),
            "tools": dict(self.tools),
            "raw_actions": dict(self.raw_actions),
            "unmapped_actions": dict(self.unmapped_actions),
            "unmapped_keys": dict(self.unmapped_keys),
        }


def is_negative_json(path: Path) -> bool:
    """文件名含 ``_neg_`` 的规划/反思负例。"""
    return "_neg_" in path.name or path.name.endswith("_neg.json")


def is_positive_json(path: Path, split: str) -> bool:
    """训练集只收 ``*_translate.json``；测试集收不含负例标记的 ``*.json``。"""
    if is_negative_json(path):
        return False
    if split == "train":
        return path.name.endswith("_translate.json")
    return path.suffix == ".json"


def _position(raw: Any) -> tuple[int, int] | None:
    """从 ``{width, height}`` 取出视图像素 ``(x, y)``。"""
    if not isinstance(raw, dict):
        return None
    if "width" not in raw or "height" not in raw:
        return None
    try:
        return int(raw["width"]), int(raw["height"])
    except (TypeError, ValueError):
        return None


def _in_view(x: int, y: int, width: int, height: int) -> bool:
    """坐标必须落在图像宽高内，与桌面工具出界拒绝一致。"""
    return 0 <= x < width and 0 <= y < height


def _normalize_key(raw: str) -> str | None:
    """把数据集键名收成本仓库白名单键；无法映射则返回 ``None``。"""
    key = raw.strip()
    if not key:
        return None
    lowered = key.lower()
    mapped = KEY_MAP.get(lowered, lowered)
    if mapped in NAMED_KEYS:
        return mapped
    if len(mapped) == 1 and (mapped.isalnum() or mapped in {".", ",", "-", "=", "[", "]", "`"}):
        return mapped
    return None


def _split_combo(raw: str) -> list[str]:
    """``Ctrl+S`` 这类字符串拆成键序列。"""
    if "+" in raw and raw.strip() != "+":
        return [part.strip() for part in raw.split("+") if part.strip()]
    return [raw]


def map_keys(raw: Any) -> list[str] | None:
    """键盘键名列表；任一键无法映射则整组失败。"""
    parts: list[str]
    if isinstance(raw, list):
        parts = [str(item) for item in raw]
    elif isinstance(raw, str):
        parts = _split_combo(raw)
    else:
        return None
    mapped: list[str] = []
    for part in parts:
        key = _normalize_key(part)
        if key is None:
            return None
        mapped.append(key)
    return mapped or None


def stage_of(actions: Sequence[dict[str, Any]]) -> str:
    """按第一条动作类型打 ``plan`` / ``act`` / ``reflect``。"""
    if not actions:
        return "act"
    first = str(actions[0].get("action_type") or "")
    if first == "PlanAction":
        return "plan"
    if first == "EvaluateSubTaskAction":
        return "reflect"
    return "act"


def extract_subtask(record: dict[str, Any]) -> str:
    """优先 ``current_task``，否则从中英文提示里抠当前子任务。"""
    current = record.get("current_task")
    if isinstance(current, str) and current.strip():
        return current.strip()
    prompt_zh = str(record.get("send_prompt_zh") or record.get("send_prompt") or "")
    match = SUBTASK_RE.search(prompt_zh)
    if match:
        return match.group(1).strip()
    prompt_en = str(record.get("send_prompt_en") or "")
    match_en = SUBTASK_EN_RE.search(prompt_en)
    if match_en:
        return match_en.group(1).strip()
    return ""


def map_mouse(action: dict[str, Any], width: int, height: int) -> dict[str, Any] | str:
    """映射鼠标动作；失败返回原因字符串。"""
    kind = str(action.get("mouse_action_type") or "").lower()
    button = str(action.get("mouse_button") or "left").lower() or "left"
    pos = _position(action.get("mouse_position"))
    if kind in {"click", "double_click"}:
        if pos is None:
            return "mouse_missing_position"
        x, y = pos
        if not _in_view(x, y, width, height):
            return "mouse_out_of_view"
        clicks = 2 if kind == "double_click" else 1
        return {"tool": "mouse_click", "args": {"x": x, "y": y, "button": button, "clicks": clicks}}
    if kind == "move":
        if pos is None:
            return "mouse_missing_position"
        x, y = pos
        if not _in_view(x, y, width, height):
            return "mouse_out_of_view"
        return {"tool": "mouse_move", "args": {"x": x, "y": y}}
    if kind == "drag":
        if pos is None:
            return "mouse_missing_position"
        x, y = pos
        if not _in_view(x, y, width, height):
            return "mouse_out_of_view"
        # 原始标注只给终点，起点是当时指针位置。
        return {"tool": "mouse_drag", "args": {"x2": x, "y2": y, "button": button}}
    if kind in {"scroll_up", "scroll_down"}:
        repeat = action.get("scroll_repeat")
        try:
            clicks = int(repeat) if repeat is not None else 1
        except (TypeError, ValueError):
            clicks = 1
        if clicks == 0:
            clicks = 1
        if kind == "scroll_down":
            clicks = -abs(clicks)
        else:
            clicks = abs(clicks)
        mapped: dict[str, Any] = {"tool": "mouse_scroll", "args": {"clicks": clicks}}
        if pos is not None:
            x, y = pos
            if not _in_view(x, y, width, height):
                return "mouse_out_of_view"
            mapped["args"]["x"] = x
            mapped["args"]["y"] = y
        return mapped
    return f"mouse_unmapped:{kind}"


def map_keyboard(action: dict[str, Any]) -> dict[str, Any] | str:
    """映射键盘动作；失败返回原因字符串。"""
    kind = str(action.get("keyboard_action_type") or "").lower()
    text = action.get("keyboard_text") or action.get("keyboard_input")
    if kind in {"text", "input"} or (kind == "" and isinstance(text, str) and text):
        if not isinstance(text, str) or not text:
            return "keyboard_missing_text"
        return {"tool": "keyboard_type", "args": {"text": text}}
    if kind in {"press", "down", "up"} or action.get("keyboard_key") is not None:
        keys = map_keys(action.get("keyboard_key"))
        if keys is None:
            return "keyboard_unmapped_key"
        return {"tool": "keyboard_press", "args": {"keys": keys}}
    return f"keyboard_unmapped:{kind}"


def map_actions(
    raw_actions: Sequence[dict[str, Any]],
    width: int,
    height: int,
    stats: ConvertStats,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """映射可执行动作；同一步的 ``down``+``up`` 合成拖拽。

    返回 ``(mapped, plan_steps, skip_reasons)``。
    """
    mapped: list[dict[str, Any]] = []
    plan_steps: list[str] = []
    skips: list[str] = []
    pending_down: dict[str, Any] | None = None

    def flush_down() -> None:
        """未配对的 ``down`` 记为无法映射。"""
        nonlocal pending_down
        if pending_down is not None:
            stats.unmapped_actions["MouseAction.down"] += 1
            skips.append("mouse_unmapped:down")
            pending_down = None

    for action in raw_actions:
        if not isinstance(action, dict):
            skips.append("action_not_object")
            continue
        action_type = str(action.get("action_type") or "")
        stats.raw_actions[action_type or "unknown"] += 1
        if action_type == "PlanAction":
            flush_down()
            element = action.get("element")
            if isinstance(element, str) and element.strip():
                plan_steps.append(element.strip())
            continue
        if action_type == "EvaluateSubTaskAction":
            flush_down()
            continue
        if action_type == "WaitAction":
            flush_down()
            stats.unmapped_actions["WaitAction"] += 1
            skips.append("wait_skipped")
            continue
        if action_type == "MouseAction":
            kind = str(action.get("mouse_action_type") or "").lower()
            if kind == "down":
                flush_down()
                pending_down = action
                continue
            if kind == "up":
                if pending_down is not None:
                    start = _position(pending_down.get("mouse_position"))
                    end = _position(action.get("mouse_position"))
                    button = str(
                        action.get("mouse_button") or pending_down.get("mouse_button") or "left"
                    ).lower()
                    pending_down = None
                    if start is None or end is None:
                        skips.append("mouse_missing_position")
                        continue
                    x1, y1 = start
                    x2, y2 = end
                    if not _in_view(x1, y1, width, height) or not _in_view(x2, y2, width, height):
                        skips.append("mouse_out_of_view")
                        continue
                    mapped.append(
                        {
                            "tool": "mouse_drag",
                            "args": {
                                "x1": x1,
                                "y1": y1,
                                "x2": x2,
                                "y2": y2,
                                "button": button,
                            },
                        }
                    )
                    stats.tools["mouse_drag"] += 1
                else:
                    stats.unmapped_actions["MouseAction.up"] += 1
                    skips.append("mouse_unmapped:up")
                continue
            flush_down()
            result = map_mouse(action, width, height)
            if isinstance(result, str):
                stats.unmapped_actions[f"MouseAction.{kind or 'unknown'}"] += 1
                skips.append(result)
                continue
            mapped.append(result)
            stats.tools[str(result["tool"])] += 1
            continue
        if action_type == "KeyboardAction":
            flush_down()
            result = map_keyboard(action)
            if isinstance(result, str):
                if result == "keyboard_unmapped_key":
                    stats.unmapped_keys[str(action.get("keyboard_key"))] += 1
                stats.unmapped_actions["KeyboardAction"] += 1
                skips.append(result)
                continue
            mapped.append(result)
            stats.tools[str(result["tool"])] += 1
            continue
        flush_down()
        stats.unmapped_actions[action_type or "unknown"] += 1
        skips.append(f"action_unmapped:{action_type or 'unknown'}")
    flush_down()
    return mapped, plan_steps, skips


def resolve_image(session_dir: Path, saved_name: str | None) -> Path | None:
    """在 ``images/`` 或 session 根目录找对应截图。"""
    if not saved_name:
        return None
    candidates = (session_dir / "images" / saved_name, session_dir / saved_name)
    for path in candidates:
        if path.is_file():
            return path
    return None


def convert_record(
    path: Path,
    split: str,
    project_root: Path,
    stats: ConvertStats,
) -> dict[str, Any] | None:
    """把单条原始 JSON 转成统一样本；失败返回 ``None``。"""
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        stats.skipped["invalid_json"] += 1
        return None
    if not isinstance(record, dict):
        stats.skipped["invalid_json"] += 1
        return None

    session_id = str(record.get("session_id") or path.parent.name)
    instruction = str(record.get("task_prompt_zh") or record.get("task_prompt") or "").strip()
    if not instruction:
        stats.skipped["missing_instruction"] += 1
        return None

    try:
        width = int(record.get("video_width") or IMAGE_WIDTH)
        height = int(record.get("video_height") or IMAGE_HEIGHT)
    except (TypeError, ValueError):
        width, height = IMAGE_WIDTH, IMAGE_HEIGHT
    if width <= 0 or height <= 0:
        width, height = IMAGE_WIDTH, IMAGE_HEIGHT

    image_path = resolve_image(path.parent, record.get("saved_image_name"))
    if image_path is None:
        stats.skipped["missing_image"] += 1
        return None

    raw_actions = record.get("actions") or []
    if not isinstance(raw_actions, list):
        stats.skipped["invalid_actions"] += 1
        return None

    mapped, plan_steps, _skips = map_actions(raw_actions, width, height, stats)
    stage = stage_of([a for a in raw_actions if isinstance(a, dict)])
    target = str(
        record.get("LLM_response_editer_zh") or record.get("LLM_response_editer") or ""
    ).strip()
    sample: dict[str, Any] = {
        "source": "screenagent",
        "split": split,
        "session_id": session_id,
        "stage": stage,
        "instruction": instruction,
        "subtask": extract_subtask(record),
        "image": image_path.resolve().relative_to(project_root.resolve()).as_posix(),
        "image_size": [width, height],
        "target": target,
        "actions": mapped,
    }
    if stage == "plan" and plan_steps:
        sample["plan"] = plan_steps
    if stage == "reflect":
        eval_action = next(
            (
                a
                for a in raw_actions
                if isinstance(a, dict) and a.get("action_type") == "EvaluateSubTaskAction"
            ),
            None,
        )
        if eval_action:
            sample["situation"] = eval_action.get("situation")
            if eval_action.get("advice"):
                sample["advice"] = eval_action.get("advice")
    stats.stages[stage] += 1
    stats.written += 1
    return sample


def iter_split_json(raw_root: Path, split: str) -> Iterable[Path]:
    """按 split 扫描 JSON，目录不存在则空。"""
    split_dir = raw_root / split
    if not split_dir.is_dir():
        return []
    return sorted(split_dir.rglob("*.json"))


def convert_split(
    raw_root: Path,
    split: str,
    project_root: Path,
    stats: ConvertStats,
) -> list[dict[str, Any]]:
    """转换一个 split，返回写出用的样本列表。"""
    samples: list[dict[str, Any]] = []
    session_ids: set[str] = set()
    for path in iter_split_json(raw_root, split):
        if is_negative_json(path):
            stats.skipped_neg += 1
            continue
        if not is_positive_json(path, split):
            stats.skipped["unexpected_name"] += 1
            continue
        stats.positive_json += 1
        sample = convert_record(path, split, project_root, stats)
        if sample is None:
            continue
        samples.append(sample)
        session_ids.add(sample["session_id"])
    stats.sessions[split] = len(session_ids)
    return samples


def write_jsonl(path: Path, samples: Sequence[dict[str, Any]]) -> None:
    """逐行写入 JSONL，保证中文不被转义。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample, ensure_ascii=False) + "\n")


def pick_preview(samples: Sequence[dict[str, Any]], stage: str, limit: int) -> list[dict[str, Any]]:
    """按 session 去重后抽取指定 stage 的样本，供人工核对。"""
    seen: set[str] = set()
    picked: list[dict[str, Any]] = []
    for sample in samples:
        if sample.get("stage") != stage:
            continue
        session = str(sample.get("session_id") or "")
        if session in seen:
            continue
        seen.add(session)
        picked.append(sample)
        if len(picked) >= limit:
            break
    return picked


def render_stats_md(stats: ConvertStats) -> str:
    """中文统计报告。"""
    lines = [
        "# ScreenAgent 预处理统计",
        "",
        f"- 训练 session：{stats.sessions.get('train', 0)}",
        f"- 测试 session：{stats.sessions.get('test', 0)}",
        f"- 正例 JSON：{stats.positive_json}",
        f"- 跳过负例 JSON：{stats.skipped_neg}",
        f"- 写出样本：{stats.written}",
        "",
        "## 阶段条数",
        "",
    ]
    for name, count in stats.stages.most_common():
        lines.append(f"- {name}：{count}")
    lines.extend(["", "## 映射后工具频次", ""])
    for name, count in stats.tools.most_common():
        lines.append(f"- `{name}`：{count}")
    lines.extend(["", "## 原始 action_type", ""])
    for name, count in stats.raw_actions.most_common():
        lines.append(f"- `{name}`：{count}")
    if stats.skipped:
        lines.extend(["", "## 丢弃样本", ""])
        for name, count in stats.skipped.most_common():
            lines.append(f"- {name}：{count}")
    if stats.unmapped_actions:
        lines.extend(["", "## 未映射动作（样本仍保留）", ""])
        for name, count in stats.unmapped_actions.most_common():
            lines.append(f"- `{name}`：{count}")
    if stats.unmapped_keys:
        lines.extend(["", "## 未映射键名", ""])
        for name, count in stats.unmapped_keys.most_common():
            lines.append(f"- `{name}`：{count}")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """命令行参数。"""
    parser = argparse.ArgumentParser(description="预处理 ScreenAgent 数据集")
    parser.add_argument(
        "--raw",
        type=Path,
        default=DEFAULT_RAW,
        help="含 train/ 与 test/ 的原始目录",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="JSONL 与统计输出目录",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="用于把截图路径写成仓库相对路径",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """转换 train/test 并写统计。缺少原始目录时返回 1。"""
    args = parse_args(argv)
    raw_root: Path = args.raw
    if not (raw_root / "train").is_dir():
        print(f"找不到训练集：{raw_root / 'train'}", file=sys.stderr)
        return 1
    if not (raw_root / "test").is_dir():
        print(f"找不到测试集：{raw_root / 'test'}", file=sys.stderr)
        return 1

    stats = ConvertStats()
    train = convert_split(raw_root, "train", args.project_root, stats)
    test = convert_split(raw_root, "test", args.project_root, stats)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "train.jsonl", train)
    write_jsonl(out / "test.jsonl", test)
    preview = pick_preview(train, "plan", 10) + pick_preview(train, "act", 10)
    write_jsonl(out / "preview.jsonl", preview)
    (out / "stats.json").write_text(
        json.dumps(stats.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "stats.md").write_text(render_stats_md(stats), encoding="utf-8")
    print(f"train={len(train)} test={len(test)} sessions={stats.sessions} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
