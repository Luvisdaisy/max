"""Online-Mind2Web 受控评测适配层。

对外导出任务加载、浏览器编排、v2 轨迹和报告能力。该包不下载数据、不保存凭据，且只有调用方显式
启动运行器时才会访问真实网站。
"""

from max_gui.mind2web.models import OnlineMind2WebTask, PreflightResult, SafetyManifest
from max_gui.mind2web.tasks import load_safety_manifest, load_tasks

__all__ = [
    "OnlineMind2WebTask",
    "PreflightResult",
    "SafetyManifest",
    "load_safety_manifest",
    "load_tasks",
]
