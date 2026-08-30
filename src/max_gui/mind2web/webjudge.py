"""以显式凭据运行上游 Online-Mind2Web WebJudge。

凭据只通过子进程环境传递，不写入 manifest、结果 JSON 或日志。调用者必须已完成本地 v2 验证。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from max_gui.mind2web.trajectory import validate_v2


class WebJudgeError(RuntimeError):
    """WebJudge 配置或子进程执行失败时抛出。"""


def run_webjudge(
    *,
    upstream_root: Path,
    trajectories_dir: Path,
    output_path: Path,
    judge_model: str,
    api_key_env: str,
    api_key: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, int]:
    """串行调用上游 WebJudge，且先验证全部轨迹。

    参数：`api_key_env` 指定凭据环境变量名，`api_key` 可由调用方临时注入而不落盘。
    异常：缺凭据、轨迹无效或评测器非零退出时抛出 `WebJudgeError`。
    """
    secret = api_key or os.environ.get(api_key_env)
    if not secret:
        raise WebJudgeError(f"未配置 WebJudge 凭据环境变量：{api_key_env}")
    results = sorted(trajectories_dir.glob("*/result.json"))
    if not results:
        raise WebJudgeError("没有可提交 WebJudge 的 result.json")
    for result in results:
        validate_v2(json.loads(result.read_text(encoding="utf-8")), result.parent)
    script = upstream_root / "src" / "run.py"
    if not script.is_file():
        raise WebJudgeError("上游克隆缺少 src/run.py")
    output_path.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, api_key_env: secret}
    command = [
        sys.executable,
        str(script),
        "--trajectories_dir",
        str(trajectories_dir),
        "--output_path",
        str(output_path),
        "--mode",
        "WebJudge_Online_Mind2Web_eval",
        "--model",
        judge_model,
        "--num_worker",
        "1",
    ]
    completed = runner(command, env=environment, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise WebJudgeError(f"WebJudge 失败（退出码 {completed.returncode}）")
    result_files = sorted(output_path.glob("*_auto_eval_results.json"))
    if not result_files:
        raise WebJudgeError("WebJudge 未产生任务级结果")
    labels: dict[str, int] = {}
    for line in result_files[-1].read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        task_id, label = item.get("task_id"), item.get("predicted_label")
        if isinstance(task_id, str) and isinstance(label, (int, bool)):
            labels[task_id] = int(label)
    if not labels:
        raise WebJudgeError("WebJudge 输出缺少可解析标签")
    return labels
