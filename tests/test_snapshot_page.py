"""行情快照页。"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from report.hub import publish_hub
from report.snapshot_data import load_snapshot_page_context
from report.snapshot_html import build_snapshot_page
from report.web_common import web_topbar


class TestSnapshotPage(unittest.TestCase):
    def test_topbar_links(self) -> None:
        nav = web_topbar(active="snapshot", trade_date="2026-06-12")
        self.assertIn("snapshot.html?date=2026-06-12", nav)
        self.assertIn('class="active"', nav)
        self.assertIn("作战卡", nav)

    def test_build_page_structure(self) -> None:
        ctx = {
            "trade_date": "2026-06-12",
            "row_count": 2,
            "snapshot_groups": ["我的"],
            "generated_at": "2026-06-12 15:00:00",
            "snapshot_stale": False,
            "rows": [
                {
                    "group": "我的",
                    "code": "600519",
                    "name": "贵州茅台",
                    "industry": "白酒",
                    "board": "沪",
                    "price": 1800.0,
                    "pre_close": 1790.0,
                    "pct_chg": 0.56,
                    "limit_status": "",
                    "warnings": [],
                    "data_missing": False,
                },
                {
                    "group": "我的",
                    "code": "000001",
                    "name": "平安银行",
                    "industry": "银行",
                    "board": "深",
                    "price": 10.5,
                    "pre_close": 10.4,
                    "pct_chg": 0.96,
                    "limit_status": "",
                    "warnings": [],
                    "data_missing": False,
                },
            ],
        }
        page = build_snapshot_page(ctx)
        self.assertIn("snap-tab-root", page)
        self.assertIn("snap-group-btn", page)
        self.assertIn("600519", page)
        self.assertIn("贵州茅台", page)
        self.assertIn("行情快照", page)
        self.assertIn("MA5距%", page)

    @patch("report.snapshot_data.load_snapshot_cache_file", return_value=None)
    @patch("report.snapshot_data.load_quote_query_cache", return_value=None)
    @patch("report.snapshot_data.load_stocks", return_value=[])
    @patch("report.snapshot_data.build_placeholder_snapshots", return_value=[])
    def test_load_context_empty_watchlist(self, _ph, _st, _qq, _cache) -> None:
        ctx = load_snapshot_page_context(date(2026, 6, 12))
        self.assertEqual(ctx["trade_date"], "2026-06-12")
        self.assertEqual(ctx["row_count"], 0)
        self.assertEqual(ctx["source"], "watchlist_placeholder")

    def test_publish_hub_writes_snapshot(self) -> None:
        publish_hub(date(2026, 6, 12))
        snap = ROOT / "reports" / "snapshot.html"
        self.assertTrue(snap.is_file())
        text = snap.read_text(encoding="utf-8")
        self.assertIn("snap-tab-root", text)
        self.assertIn("web-topnav", text)
        index = (ROOT / "reports" / "index.html").read_text(encoding="utf-8")
        self.assertIn("snapshot.html", index)


if __name__ == "__main__":
    unittest.main()
