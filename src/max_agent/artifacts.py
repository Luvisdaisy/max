from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


def _json_line(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"


@dataclass(frozen=True, slots=True)
class ExperimentArchive:
    path: Path

    @classmethod
    def create(cls, artifact_root: Path, command: str) -> "ExperimentArchive":
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = artifact_root / f"{timestamp}-{command}"
        path.mkdir(parents=True, exist_ok=False)
        return cls(path)

    def write_config(self, payload: Mapping[str, Any]) -> None:
        lines = [f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in sorted(payload.items())]
        (self.path / "config.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_environment(self, payload: Mapping[str, Any]) -> None:
        (self.path / "environment.json").write_text(_json_line(payload), encoding="utf-8")

    def append_trajectory(self, payload: Mapping[str, Any]) -> None:
        with (self.path / "trajectory.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(_json_line(payload))

    def write_result(self, payload: Mapping[str, Any]) -> None:
        (self.path / "result.json").write_text(_json_line(payload), encoding="utf-8")
