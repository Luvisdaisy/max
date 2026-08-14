from __future__ import annotations

import argparse
import sys
from pathlib import Path

from max_gui.config import MissingVllmError, MissingWeightsError, UnknownModelError, load_settings
from max_gui.lifecycle import download_model, serve_model


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="max-gui", description="本地多模态 ReAct GUI Agent")
    parser.add_argument("--workspace", type=Path, default=None, help="工作区根目录，默认当前目录")
    parser.add_argument("--model", default=None, help="模型别名，开发默认 qwen3.5-2b")
    parser.add_argument("--new", action="store_true", help="强制创建新会话")
    sub = parser.add_subparsers(dest="command")

    tui = sub.add_parser("tui", help="启动 Textual REPL（默认）")
    tui.add_argument("--new", action="store_true", help="强制创建新会话")
    tui.add_argument("--workspace", type=Path, default=None)
    tui.add_argument("--model", default=None)

    serve = sub.add_parser("serve", help="启动本地 vLLM OpenAI 兼容服务")
    serve.add_argument("--model", default=None)
    serve.add_argument("--workspace", type=Path, default=None)

    download = sub.add_parser("download", help="通过 ModelScope 下载模型到 model/<alias>")
    download.add_argument("alias", nargs="?", default=None, help="模型别名，默认 qwen3.5-2b")
    download.add_argument("--workspace", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "tui"
    try:
        settings = load_settings(
            workspace=getattr(args, "workspace", None),
            model=getattr(args, "model", None) or getattr(args, "alias", None),
        )
    except UnknownModelError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc

    if command == "download":
        path = download_model(settings, getattr(args, "alias", None))
        print(f"已下载到 {path}")
        return
    if command == "serve":
        try:
            raise SystemExit(serve_model(settings))
        except (MissingWeightsError, MissingVllmError) as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
    from max_gui.app import run_app

    force_new = bool(getattr(args, "new", False))
    run_app(settings, force_new=force_new)
