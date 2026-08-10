"""测试套件共享配置；保持为空以避免引入隐式全局行为。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
