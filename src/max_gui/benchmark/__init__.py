"""本地 GUI Agent 任务评测。

对外导出任务加载、测试场应用与独立评分入口；Agent 仍只能经截图和桌面工具操作浏览器。
"""

from max_gui.benchmark.evaluator import score_state
from max_gui.benchmark.tasks import BenchmarkTask, load_task_suite
from max_gui.benchmark.web import create_benchmark_app

__all__ = ["BenchmarkTask", "create_benchmark_app", "load_task_suite", "score_state"]
