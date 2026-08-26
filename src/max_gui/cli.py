"""命令行入口：解析参数并分发 TUI 与 vLLM 服务。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from max_gui.cleanup import cleanup_record_directories
from max_gui.config import (
    MissingVllmError,
    MissingWeightsError,
    load_settings,
)
from max_gui.lifecycle import serve_model
from max_gui.provider import (
    MissingProviderKeyError,
    ServeNotAllowedError,
    UnknownProviderError,
    get_provider,
    require_provider_key,
)


def build_parser() -> argparse.ArgumentParser:
    """构造 `max-gui` 参数解析器。

    无子命令时等价于 `tui`。全局与 `tui` 接受 `--workspace` / `--new`。
    模型与后端只从 `.env` 读取，不提供 `--model`。

    返回：
        配置好子命令的 `ArgumentParser`。
    """
    parser = argparse.ArgumentParser(prog="max-gui", description="本地多模态 ReAct GUI Agent")
    parser.add_argument("--workspace", type=Path, default=None, help="工作区根目录，默认当前目录")
    parser.add_argument("--new", action="store_true", help="强制创建新会话")
    parser.add_argument("--benchmark", action="store_true", help="启动本地 GUI 评测首页")
    sub = parser.add_subparsers(dest="command")

    tui = sub.add_parser("tui", help="启动 Textual REPL（默认）")
    tui.add_argument("--new", action="store_true", help="强制创建新会话")
    tui.add_argument("--workspace", type=Path, default=None)

    serve = sub.add_parser("serve", help="启动本地 vLLM OpenAI 兼容服务")
    serve.add_argument("--workspace", type=Path, default=None)

    cleanup = sub.add_parser("cleanup", help="清除截图、运行和会话记录")
    cleanup.add_argument("--workspace", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> None:
    """解析命令行并执行对应子命令。

    参数：
        argv: 参数列表；`None` 时读 `sys.argv[1:]`。

    异常：
        SystemExit: 非法 provider 退出码 2；缺密钥、缺 Workspace、缺权重、
            非 local 下 serve 或找不到 vLLM 退出码 1；`serve` 成功时以
            vLLM 进程退出码结束。
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "tui"
    try:
        settings = load_settings(workspace=getattr(args, "workspace", None))
    except UnknownProviderError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc

    if command == "cleanup":
        raise SystemExit(_run_cleanup(settings))
    if command == "serve":
        try:
            raise SystemExit(serve_model(settings))
        except (MissingWeightsError, MissingVllmError, ServeNotAllowedError) as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
    if args.benchmark:
        from max_gui.benchmark.service import run_benchmark_server

        run_benchmark_server(settings)
        return
    try:
        require_provider_key(get_provider(settings.provider), settings.api_key)
    except MissingProviderKeyError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    from max_gui.app import run_app

    force_new = bool(getattr(args, "new", False))
    run_app(settings, force_new=force_new)


def _run_cleanup(settings) -> int:
    """直接清理当前项目的截图、运行与会话记录。

    参数：
        settings: 已解析的运行配置，用于确定项目根与会话、截图目录。

    返回：
        清理成功或用户取消时为 0；发生文件系统错误时为 1。

    异常：
        ValueError: 配置中的清理目标逃出项目根目录。
    """
    directories = {
        "截图": settings.screenshots_dir,
        "运行": settings.project_root / "artifacts" / "runs",
        "会话": settings.sessions_dir,
    }
    report = cleanup_record_directories(settings.project_root, directories)
    for label, count in report.removed.items():
        print(f"{label}记录：已清理 {count} 项。")
    for error in report.errors:
        print(f"清理失败：{error}", file=sys.stderr)
    return 0 if report.succeeded else 1
