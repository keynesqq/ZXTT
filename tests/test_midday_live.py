"""午间进度页冒烟。"""
from __future__ import annotations

import sys
import unittest
from datetime import date

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from report.midday_live import build_midday_live_page

_DAY = date(2026, 6, 10)


class TestMiddayLive(unittest.TestCase):
    def test_live_page_title(self) -> None:
        status = {
            "trade_date": _DAY.isoformat(),
            "status": "running",
            "current_label": "④ AI 研判合成",
            "detail": "测试",
            "progress_pct": 50,
            "steps_done": ["collect"],
        }
        page = build_midday_live_page(status)
        self.assertIn("午间作战卡", page)
        self.assertIn("midday_run", page)


if __name__ == "__main__":
    unittest.main()
