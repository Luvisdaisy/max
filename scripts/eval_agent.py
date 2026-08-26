"""启动本地 Web GUI 基准测试场。

此命令只启动回环服务；评测运行器需在专用浏览器窗口已打开时调用 `run_task`，避免脚本未经
用户确认驱动真实桌面。
"""

from __future__ import annotations

import argparse

import uvicorn

from max_gui.benchmark.tasks import load_task_suite
from max_gui.benchmark.web import create_benchmark_app


def main() -> int:
    """启动回环测试场，返回服务退出码。"""
    parser = argparse.ArgumentParser(description="启动本地 GUI Agent Web 评测场")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise ValueError("端口必须在 1 至 65535 之间")
    uvicorn.run(create_benchmark_app(load_task_suite()), host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
