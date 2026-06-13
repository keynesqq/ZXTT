"""自选刷新与报告分组对齐。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))


class WatchlistRefreshTests(unittest.TestCase):
    def test_align_group_order_for_reports(self) -> None:
        from watchlist.refresh import align_group_order_for_reports

        with patch("watchlist.loader.watchlist_group_names", return_value=["想买的", "我的"]):
            out = align_group_order_for_reports(["我的", "高度关注", "想买的"])
        self.assertEqual(out, ["想买的", "我的"])

    def test_codes_match_watchlist(self) -> None:
        from watchlist.refresh import codes_match_watchlist

        rows = [{"code": "600519", "group": "我的"}, {"code": "000001", "group": "想买的"}]
        with patch("watchlist.refresh.current_watchlist_codes", return_value={"600519", "000001"}):
            self.assertTrue(codes_match_watchlist(rows))
        with patch("watchlist.refresh.current_watchlist_codes", return_value={"600519"}):
            self.assertFalse(codes_match_watchlist(rows))

    def test_refresh_clears_snapshot_cache(self) -> None:
        from watchlist.refresh import refresh_watchlist_pages

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            snap = data / "snapshot_2026-06-12.json"
            snap.write_text('{"schema_version":2,"rows":[{"code":"1"}]}', encoding="utf-8")
            with patch("watchlist.refresh.snapshot_cache_path", return_value=snap):
                with patch("quote.query.query_quotes", return_value=([], None, {"code_count": 0})):
                    with patch("report.hub.publish_snapshot"):
                        with patch("report.hub.publish_hub"):
                            with patch("report.hub.refresh_hub_feed"):
                                with patch(
                                    "watchlist.loader.watchlist_source_summary",
                                        return_value={"watchlist_stock_count": 0},
                                ):
                                    refresh_watchlist_pages(on_date=__import__("datetime").date(2026, 6, 12))
            self.assertFalse(snap.is_file())


if __name__ == "__main__":
    unittest.main()
