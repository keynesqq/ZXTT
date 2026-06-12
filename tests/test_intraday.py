from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from intraday.mock import DEMO_DATE_ISO, MOCK_STOCKS, build_mock_series_points
from intraday.resume import phase_status, resolve_phases
from intraday.simulate import run_intraday_simulate
from intraday.series import (
    append_intraday_segment_point,
    load_intraday_segment,
    load_intraday_series,
    write_merged_intraday_series,
)
from intraday.stocks import resolve_intraday_stocks
from intraday.watch import _schedule_afternoon, _schedule_morning, _schedule_times, run_intraday_watch
from quote.snapshot.build import SnapshotRow
from watchlist.ths_blocks import StockItem, ThsBlocksError


def _mock_snapshot_row(code: str, captured_at: str) -> SnapshotRow:
    return SnapshotRow(
        code=code,
        name=code,
        group="我的",
        block_id="",
        price=10.5,
        pre_close=10.0,
        open=10.1,
        high=10.6,
        low=10.0,
        pct_chg=5.0,
        snapshot_at=captured_at,
        quote_fetched_at=captured_at,
    )


class IntradayStocksTests(unittest.TestCase):
    def test_codes_normalized_and_deduped(self):
        stocks = resolve_intraday_stocks(["600519", "1", "600519"])
        self.assertEqual([s.code for s in stocks], ["600519", "000001"])

    def test_default_dedupes_watchlist_across_groups(self):
        dup = [
            StockItem(code="600519", name="茅台", group="我的", block_id="a"),
            StockItem(code="600519", name="茅台", group="想买的", block_id="b"),
            StockItem(code="000001", name="平安", group="我的", block_id="c"),
        ]
        with patch("intraday.stocks.load_stocks", return_value=dup):
            stocks = resolve_intraday_stocks(None)
        self.assertEqual([s.code for s in stocks], ["600519", "000001"])
        self.assertEqual(stocks[0].group, "我的")

    @patch("intraday.stocks.load_stocks", side_effect=ThsBlocksError("no ths"))
    @patch("morning.codes.load_stocks", return_value=[])
    @patch("morning.codes.load_quote_query_cache", return_value=None)
    @patch("intraday.stocks.intraday_cfg", return_value={"codes": ["300750", "300750"]})
    def test_fallback_codes_from_config(self, _cfg, _cache, _stocks, _load):
        stocks = resolve_intraday_stocks(None)
        self.assertEqual([s.code for s in stocks], ["300750"])


class IntradayResumeTests(unittest.TestCase):
    def test_resolve_phases_resume_skips_done(self):
        day = date(2026, 6, 12)
        with (
            patch("intraday.resume.auction_phase_complete", return_value=True),
            patch("intraday.resume.intraday_segment_complete", side_effect=lambda _d, seg: seg == "morning"),
        ):
            phases = resolve_phases(session="all", resume=True, on_date=day)
        self.assertEqual(phases, ["afternoon"])


class IntradayScheduleTests(unittest.TestCase):
    def test_default_schedule_covers_morning_session(self):
        day = date(2026, 6, 12)
        schedule, interval = _schedule_morning(day)
        self.assertEqual(interval, 60)
        self.assertEqual(schedule[0].strftime("%H:%M:%S"), "09:30:00")
        self.assertEqual(schedule[-1].strftime("%H:%M:%S"), "11:30:00")
        self.assertEqual(len(schedule), 121)

    def test_default_schedule_covers_afternoon_session(self):
        day = date(2026, 6, 12)
        schedule, interval = _schedule_afternoon(day)
        self.assertEqual(interval, 60)
        self.assertEqual(schedule[0].strftime("%H:%M:%S"), "13:00:00")
        self.assertEqual(schedule[-1].strftime("%H:%M:%S"), "15:00:00")
        self.assertEqual(len(schedule), 121)

    def test_schedule_times_alias_morning(self):
        day = date(2026, 6, 12)
        morning, _ = _schedule_morning(day)
        alias, _ = _schedule_times(day)
        self.assertEqual(morning, alias)


class IntradaySeriesTests(unittest.TestCase):
    def test_segment_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            with patch("intraday.series.DATA_DIR", data):
                row = {"code": "600519", "name": "茅台", "price": 10.5}
                append_intraday_segment_point(
                    [row],
                    captured_at="2026-06-09 09:30:00",
                    on_date=date(2026, 6, 9),
                    segment="morning",
                )
                loaded = load_intraday_segment(on_date=date(2026, 6, 9), segment="morning")
                self.assertEqual(len(loaded), 1)
                self.assertEqual(loaded[0]["rows"][0]["code"], "600519")

    def test_merge_series(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            with patch("intraday.series.DATA_DIR", data):
                day = date(2026, 6, 12)
                append_intraday_segment_point(
                    [{"code": "600519"}],
                    captured_at="2026-06-12 11:30:00",
                    on_date=day,
                    segment="morning",
                    is_final=True,
                )
                append_intraday_segment_point(
                    [{"code": "600519"}],
                    captured_at="2026-06-12 13:00:00",
                    on_date=day,
                    segment="afternoon",
                    is_final=True,
                )
                write_merged_intraday_series(on_date=day)
                merged = load_intraday_series(on_date=day)
                self.assertEqual(len(merged), 2)


class IntradayWatchTests(unittest.TestCase):
    def test_watch_full_day_resets_and_merges(self):
        day = date(2026, 6, 12)
        stocks = [StockItem(code="600519", name="茅台", group="我的", block_id="")]
        snap = _mock_snapshot_row("600519", "2026-06-12 09:30:00")
        auction_ok = {
            "outcome": "ok",
            "point_count": 1,
            "trend_path": "data/auction_trend_2026-06-12.json",
        }
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            with (
                patch("intraday.series.DATA_DIR", data),
                patch("intraday.manifest.DATA_DIR", data),
                patch("intraday.watch.resolve_intraday_stocks", return_value=stocks),
                patch("intraday.watch.build_snapshots", return_value=[snap]),
                patch("intraday.watch.run_auction_watch", return_value=auction_ok),
                patch("intraday.watch._sleep_until"),
                patch("intraday.watch.is_trading_day", return_value=True),
            ):
                result = run_intraday_watch(["600519"], force=True, on_date=day, session="all")
                self.assertEqual(result["outcome"], "ok")
                self.assertEqual(result["auction_point_count"], 1)
                self.assertEqual(result["morning_point_count"], 1)
                self.assertEqual(result["afternoon_point_count"], 1)
                self.assertEqual(result["merged_point_count"], 2)
                self.assertTrue((data / f"intraday_series_{day.isoformat()}.json").is_file())

    def test_watch_error_writes_manifest(self):
        day = date(2026, 6, 12)
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            with (
                patch("intraday.series.DATA_DIR", data),
                patch("intraday.manifest.DATA_DIR", data),
                patch(
                    "intraday.watch.resolve_intraday_stocks",
                    return_value=[StockItem(code="600519", name="茅台", group="", block_id="")],
                ),
                patch("intraday.watch.run_auction_watch", return_value={"outcome": "ok", "point_count": 1}),
                patch("intraday.watch.build_snapshots", side_effect=RuntimeError("quote down")),
                patch("intraday.watch._sleep_until"),
                patch("intraday.watch.is_trading_day", return_value=True),
            ):
                result = run_intraday_watch(["600519"], force=True, on_date=day)
                self.assertEqual(result["outcome"], "error")
                manifest = json.loads((data / "last_intraday_watch.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["outcome"], "error")
                self.assertIn("quote down", manifest["message"])


class IntradaySimulateTests(unittest.TestCase):
    def test_mock_schedule_point_count(self):
        day = date.fromisoformat(DEMO_DATE_ISO)
        morning, interval = _schedule_morning(day)
        afternoon, _ = _schedule_afternoon(day)
        morning_points = build_mock_series_points(morning, segment="morning")
        afternoon_points = build_mock_series_points(afternoon, segment="afternoon")
        self.assertEqual(interval, 60)
        self.assertEqual(len(morning_points), 121)
        self.assertEqual(len(afternoon_points), 121)

    def test_simulate_full_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            with (
                patch("intraday.series.DATA_DIR", data),
                patch("intraday.manifest.DATA_DIR", data),
                patch("auction.series.DATA_DIR", data),
                patch("auction.manifest.DATA_DIR", data),
                patch("auction.trajectory.DATA_DIR", data),
            ):
                result = run_intraday_simulate(on_date=date.fromisoformat(DEMO_DATE_ISO))
                self.assertEqual(result["outcome"], "ok")
                self.assertGreaterEqual(int(result["auction_point_count"] or 0), 20)
                self.assertEqual(result["morning_point_count"], 121)
                self.assertEqual(result["afternoon_point_count"], 121)
                self.assertEqual(result["merged_point_count"], 242)
                day_iso = DEMO_DATE_ISO
                self.assertTrue((data / f"auction_trend_{day_iso}.json").is_file())
                self.assertTrue((data / f"intraday_series_{day_iso}_morning.json").is_file())
                self.assertTrue((data / f"intraday_series_{day_iso}_afternoon.json").is_file())
                self.assertTrue((data / f"intraday_series_{day_iso}.json").is_file())


if __name__ == "__main__":
    unittest.main()
