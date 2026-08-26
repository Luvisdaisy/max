"""通过 OpenAI 兼容 vLLM 端点对比基础模型与 LoRA 模型的动作格式。"""

from __future__ import annotations

import argparse
import base64
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = (
    PROJECT_ROOT / "artifacts" / "datasets" / "screenagent" / "processed" / "test.jsonl"
)


def expected_actions(record: dict[str, Any]) -> list[dict[str, Any]]:
    """提取 act 样本的标准工具动作；非 act 样本不计入动作准确率。"""
    return list(record.get("actions") or []) if record.get("stage") == "act" else []


def parse_actions(content: str) -> list[dict[str, Any]] | None:
    """从模型文本读取 JSON 数组，格式错误时返回 ``None``。"""
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        return None
    return value


def request_payload(record: dict[str, Any], image_path: Path, model: str) -> dict[str, Any]:
    """构建发送给 vLLM Chat Completions 的单样本评估请求。"""
    image = base64.b64encode(image_path.read_bytes()).decode("ascii")
    prompt = f"任务：{record.get('instruction', '')}\n当前子任务：{record.get('subtask', '')}\n只输出下一步 JSON 数组。"
    return {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }


def score(records: list[dict[str, Any]], results: list[str]) -> dict[str, float | int]:
    """统计 JSON 格式合规率与与标注动作完全一致的准确率。"""
    pairs = [
        (record, text)
        for record, text in zip(records, results, strict=True)
        if expected_actions(record)
    ]
    parsed = [parse_actions(text) for _, text in pairs]
    valid = sum(value is not None for value in parsed)
    exact = sum(
        value == expected_actions(record) for (record, _), value in zip(pairs, parsed, strict=True)
    )
    total = len(pairs)
    return {
        "samples": total,
        "valid_json_rate": valid / total if total else 0.0,
        "exact_action_rate": exact / total if total else 0.0,
    }


def run_model(
    records: list[dict[str, Any]], model: str, base_url: str, timeout: float
) -> list[str]:
    """逐样本请求指定模型，网络或响应结构异常会立即抛出 HTTP 错误。"""
    outputs: list[str] = []
    with httpx.Client(base_url=base_url.rstrip("/") + "/", timeout=timeout) as client:
        for record in records:
            image_path = PROJECT_ROOT / str(record["image"])
            response = client.post(
                "chat/completions", json=request_payload(record, image_path, model)
            )
            response.raise_for_status()
            payload = response.json()
            outputs.append(str(payload["choices"][0]["message"].get("content") or ""))
    return outputs


def main(argv: Sequence[str] | None = None) -> int:
    """运行两模型对比，并把可审计的指标写成 JSON。"""
    parser = argparse.ArgumentParser(description="比较基础模型与 LoRA 模型的工具动作格式")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--base-model", default="qwen3.5-4b")
    parser.add_argument("--lora-model", default="qwen3.5-4b-lora")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "artifacts" / "reports" / "lora-eval.json"
    )
    args = parser.parse_args(argv)
    records = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records = [record for record in records if expected_actions(record)][: args.limit]
    if not records:
        raise ValueError("评估集没有 act 样本")
    report = {
        "base_model": args.base_model,
        "lora_model": args.lora_model,
        "base": score(records, run_model(records, args.base_model, args.base_url, args.timeout)),
        "lora": score(records, run_model(records, args.lora_model, args.base_url, args.timeout)),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
