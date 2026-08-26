"""本地运行记录清理：安全删除截图、运行事件与会话目录内容。

对外入口为 `cleanup_record_directories`，只接受项目根目录下的记录目录，保留目录
本身，并把单个删除失败收集到报告中供 CLI 展示。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class CleanupReport:
    """记录一次清理操作的删除数量与失败信息。"""

    removed: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        """返回本次清理是否没有发生文件系统错误。"""
        return not self.errors


def cleanup_record_directories(project_root: Path, directories: dict[str, Path]) -> CleanupReport:
    """递归清理项目根目录内指定的记录目录并保留目录本身。

    参数：
        project_root: 项目根目录，所有清理目标必须位于其内部。
        directories: 记录类型到目录路径的映射。

    返回：
        `CleanupReport`，其中 `removed` 统计每个目录删除的直接条目数，`errors`
        保存无法创建目录或删除条目的中文错误。

    异常：
        ValueError: 目标目录解析后逃出项目根，或目标目录就是项目根。
    """
    root = project_root.resolve()
    report = CleanupReport()
    for label, raw_directory in directories.items():
        directory = Path(raw_directory).resolve()
        _validate_target(root, directory)
        report.removed[label] = 0
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            report.errors.append(f"{label}：无法创建目录 {directory}：{exc}")
            continue
        try:
            entries = list(directory.iterdir())
        except OSError as exc:
            report.errors.append(f"{label}：无法读取目录 {directory}：{exc}")
            continue
        for entry in entries:
            try:
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
                report.removed[label] += 1
            except OSError as exc:
                report.errors.append(f"{label}：无法删除 {entry}：{exc}")
    return report


def _validate_target(root: Path, target: Path) -> None:
    """确认清理目标位于项目根内且不是项目根本身。"""
    if target == root:
        raise ValueError(f"清理目标不能是项目根目录：{target}")
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"清理目标逃出项目根目录：{target}") from exc
