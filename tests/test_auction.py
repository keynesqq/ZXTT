from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from auction.mock import DEMO_DATE_ISO, MOCK_STOCKS, build_mock_series_points, mock_stocks
from auction.simulate import run_auction_simulate
from auction.trajectory import build_auction_trends, write_auction_trend
from auction.series import append_auction_series_point, load_auction_series
from auction.watch import _schedule_times, run_auction_watch
from quote.auction_snap import AuctionSnap
from auction.stocks import resolve_auction_codes, resolve_auction_stocks
from watchlist.ths_blocks import StockItem


def _row(code: str, gap: float, *, open_px: float | None = None, price: float = 10.0) -> dict:
    return {
        "code": code,
        "name": code,
        "group": "我的",
        "price": price,
        "pre_close": 10.0,
        "open": open_px,
        "trade_px": open_px if open_px is not None else price,
        "open_gap_pct": gap,
        "pct_chg": gap,
        "amount_yi": 0.1,
    }


class AuctionStocksTests(unittest.TestCase):
    def test_codes_normalized_and_deduped(self):
        stocks = resolve_auction_stocks(["600519", "1", "600519"])
        self.assertEqual([s.code for s in stocks], ["600519", "000001"])

    @patch("morning.codes.load_stocks", return_value=[])
    @patch("morning.codes.load_quote_query_cache", return_value=None)
    @patch("auction.stocks.auction_cfg", return_value={"codes": ["300750", "300750"]})
    def test_default_codes_from_config(self, _cfg, _cache, _stocks):
        self.assertEqual(resolve_auction_codes(None), ["300750"])


class AuctionTrajectoryTest(unittest.TestCase):
    def test_shape_rising(self):
        points = [
            {"captured_at": "09:15:05", "is_final": False, "rows": [_row("600519", 0.5)]},
            {"captured_at": "09:20:05", "is_final": False, "rows": [_row("600519", 0.9)]},
            {"captured_at": "09:25:05", "is_final": True, "rows": [_row("600519", 1.2, open_px=10.12, price=10.12)]},
        ]
        trends = build_auction_trends(points)
        self.assertEqual(len(trends), 1)
        self.assertEqual(trends[0]["shape"], "一路抬升")
        self.assertEqual(trends[0]["shape_after_920"], "一路抬升")
        self.assertEqual(trends[0]["gap_delta"], 0.7)

    def test_shape_after_920_ignores_early_noise(self):
        points = [
            {"captured_at": "09:15:05", "is_final": False, "rows": [_row("600519", 2.0)]},
            {"captured_at": "09:18:05", "is_final": False, "rows": [_row("600519", -0.5)]},
            {"captured_at": "09:21:05", "is_final": False, "rows": [_row("600519", 0.0)]},
            {"captured_at": "09:25:05", "is_final": True, "rows": [_row("600519", 0.8, open_px=10.08)]},
        ]
        trends = build_auction_trends(points)
        self.assertEqual(trends[0]["shape_after_920"], "一路抬升")

    def test_amount_delta_path(self):
        def row(code, gap, amount):
            r = _row(code, gap)
            r["amount_yi"] = amount
            return r

        points = [
            {"captured_at": "09:15:05", "is_final": False, "rows": [row("600519", 0.0, 1.0)]},
            {"captured_at": "09:20:05", "is_final": False, "rows": [row("600519", 0.5, 1.5)]},
            {"captured_at": "09:25:05", "is_final": True, "rows": [row("600519", 1.0, 2.2)]},
        ]
        trends = build_auction_trends(points)
        self.assertEqual(trends[0]["amount_delta_path"], [0.5, 0.7])
        self.assertEqual(trends[0]["amount_delta_total"], 1.2)

    def test_shape_flat(self):
        points = [
            {"captured_at": "09:15:05", "is_final": False, "rows": [_row("000001", 0.1)]},
            {"captured_at": "09:25:05", "is_final": True, "rows": [_row("000001", 0.2, open_px=10.02)]},
        ]
        trends = build_auction_trends(points)
        self.assertEqual(trends[0]["shape"], "震荡")

    def test_series_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            with patch("auction.series.DATA_DIR", data), patch("auction.trajectory.DATA_DIR", data):
                snap = AuctionSnap(code="600519", name="茅台", group="我的", price=10.5, pre_close=10.0, pct_chg=5.0)
                append_auction_series_point([snap], captured_at="2026-06-09 09:15:05", on_date=date(2026, 6, 9))
                loaded = load_auction_series(on_date=date(2026, 6, 9))
                self.assertEqual(len(loaded), 1)
                self.assertEqual(loaded[0]["rows"][0]["code"], "600519")
                path = write_auction_trend(on_date=date(2026, 6, 9), series_points=loaded)
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["point_count"], 1)


class AuctionWatchTest(unittest.TestCase):
    def test_watch_resets_series_before_collect(self):
        day = date(2026, 6, 11)
        stocks = [StockItem(code="600519", name="茅台", group="我的")]
        snap = AuctionSnap(code="600519", name="茅台", group="我的", price=10.0, pre_close=10.0)
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            with (
                patch("auction.series.DATA_DIR", data),
                patch("auction.trajectory.DATA_DIR", data),
                patch("auction.manifest.DATA_DIR", data),
                patch("auction.watch.resolve_auction_stocks", return_value=stocks),
                patch("auction.watch.build_auction_snapshots", return_value=[snap]),
                patch("auction.watch._sleep_until"),
                patch("auction.watch.is_trading_day", return_value=True),
            ):
                append_auction_series_point([snap], captured_at="2026-06-11 08:00:00", on_date=day)
                result = run_auction_watch(["600519"], force=False, on_date=day)
                self.assertEqual(result["outcome"], "ok")
                self.assertEqual(result["point_count"], 21)

    def test_watch_error_writes_manifest(self):
        day = date(2026, 6, 12)
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            with (
                patch("auction.series.DATA_DIR", data),
                patch("auction.manifest.DATA_DIR", data),
                patch(
                    "auction.watch.resolve_auction_stocks",
                    return_value=[StockItem(code="600519", name="茅台", group="", block_id="")],
                ),
                patch("auction.watch.build_auction_snapshots", side_effect=RuntimeError("quote down")),
                patch("auction.watch._sleep_until"),
                patch("auction.watch.is_trading_day", return_value=True),
            ):
                result = run_auction_watch(["600519"], force=False, on_date=day)
                self.assertEqual(result["outcome"], "error")
                manifest = json.loads((data / "last_auction_watch.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["outcome"], "error")
                self.assertIn("quote down", manifest["message"])


class AuctionSimulateTest(unittest.TestCase):
    def test_mock_schedule_point_count(self):
        day = date.fromisoformat(DEMO_DATE_ISO)
        schedule, interval = _schedule_times(day)
        points = build_mock_series_points(schedule)
        self.assertEqual(interval, 30)
        self.assertGreaterEqual(len(points), 20)
        self.assertEqual(points[0]["captured_at"], f"{DEMO_DATE_ISO} 09:15:05")
        self.assertEqual(points[-1]["captured_at"], f"{DEMO_DATE_ISO} 09:25:05")
        self.assertTrue(points[-1]["is_final"])
        self.assertEqual(len(points[0]["rows"]), len(MOCK_STOCKS))

    def test_mock_shapes_match_expected(self):
        day = date.fromisoformat(DEMO_DATE_ISO)
        schedule, _ = _schedule_times(day)
        points = build_mock_series_points(schedule)
        trends = build_auction_trends(points)
        shapes = {t["code"]: t["shape"] for t in trends}
        for stock in mock_stocks():
            with self.subTest(code=stock.code, expected=stock.expected_shape):
                self.assertEqual(shapes.get(stock.code), stock.expected_shape)

    def test_simulate_full_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            with (
                patch("auction.series.DATA_DIR", data),
                patch("auction.trajectory.DATA_DIR", data),
                patch("auction.manifest.DATA_DIR", data),
            ):
                result = run_auction_simulate(on_date=date.fromisoformat(DEMO_DATE_ISO))
                self.assertEqual(result["outcome"], "ok")
                self.assertGreaterEqual(result["point_count"], 20)
                self.assertEqual(result["stock_count"], len(MOCK_STOCKS))
                self.assertFalse(result["shape_mismatches"])
                self.assertTrue((data / f"auction_series_{DEMO_DATE_ISO}.json").is_file())
                self.assertTrue((data / f"auction_trend_{DEMO_DATE_ISO}.json").is_file())
                self.assertTrue((data / "last_auction_watch.json").is_file())
                series = json.loads((data / f"auction_series_{DEMO_DATE_ISO}.json").read_text(encoding="utf-8"))
                self.assertEqual(series.get("source"), "simulate")
                trend = json.loads((data / f"auction_trend_{DEMO_DATE_ISO}.json").read_text(encoding="utf-8"))
                self.assertEqual(len(trend["stocks"]), len(MOCK_STOCKS))


if __name__ == "__main__":
    unittest.main()
