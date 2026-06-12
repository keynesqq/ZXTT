"""晚间报告 · 中枢页应展示服务于当日的昨晚报告。"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from report.hub import aggregate_hub


class TestHubEveningServeDay(unittest.TestCase):
    def test_today_hub_links_yesterday_evening_report(self) -> None:
        hub = aggregate_hub(date(2026, 6, 12))
        evening = hub["slots"]["evening"]
        self.assertTrue(evening["report_ready"])
        self.assertEqual(evening["report_href"], "2026-06-11/daily_evening.html")
        self.assertEqual(evening["report_trade_date"], "2026-06-11")
        self.assertEqual(evening["status"], "ok")


if __name__ == "__main__":
    unittest.main()
