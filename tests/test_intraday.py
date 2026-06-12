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
    @patch("intraday.stocks.watchlist_by_code", side_effect=ThsBlocksError("no ths"))
    @patch("morning.codes.load_stocks", return_value=[])
    @patch("morning.codes.load_quote_query_cache", return_value=None)
    @patch("intraday.stocks.intraday_cfg", return_value={"codes": ["300750", "300750"]})
    def test_fallback_codes_from_config(self, _cfg, _cache, _stocks, _wl, _load):
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

    def test_resolve_phases_single_session_resume_skips_done(self):
        day = date(2026, 6, 12)
        with patch("intraday.resume.phase_complete", return_value=True):
            phases = resolve_phases(session="morning", resume=True, on_date=day)
        self.assertEqual(phases, [])

    def test_force_single_point_not_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            with patch("intraday.series.DATA_DIR", data):
                day = date(2026, 6, 12)
                append_intraday_segment_point(
                    [{"code": "600519"}],
                    captured_at="2026-06-12 09:30:00",
                    on_date=day,
                    segment="morning",
                    is_final=True,
                )
                from intraday.resume import intraday_segment_complete

                self.assertFalse(intraday_segment_complete(day, "morning"))


class IntradayScheduleTests(unittest.TestCase):
    def test_default_schedule_covers_morning_session(self):
        day = date(2026, 6, 12)
        schedule, interval = _schedule_morning(day)
        self.assertEqual(interval, 60)
        self.assertEqual(schedule[0].strftime("%H:%M:%S"), "09:30:00")
        self.assertEqual(schedule[-1].strftime("%H:%M:%S"), "11:30:00")
        self.assertEqual(len(schedule), 121)

    def test_schedule_times_alias_morning(self):
        day = date(2026, 6, 12)
        morning, _ = _schedule_morning(day)
        alias, _ = _schedule_times(day)
        self.assertEqual(morning, alias)

    def test_default_schedule_covers_afternoon_session(self):
        day = date(2026, 6, 12)
        schedule, interval = _schedule_afternoon(day)
        self.assertEqual(interval, 60)
        self.assertEqual(schedule[0].strftime("%H:%M:%S"), "13:00:00")
        self.assertEqual(schedule[-1].strftime("%H:%M:%S"), "15:00:00")
        self.assertEqual(len(schedule), 121)


class IntradayScheduleGuardTests(unittest.TestCase):
    def test_historical_date_skips_guard(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from core.schedule_guard import prepare_live_schedule

        day = date(2026, 6, 11)
        tz = ZoneInfo("Asia/Shanghai")
        schedule = [datetime(2026, 6, 11, 9, 30, tzinfo=tz), datetime(2026, 6, 11, 9, 31, tzinfo=tz)]
        with patch("core.schedule_guard.today_cn", return_value=date(2026, 6, 12)):
            out = prepare_live_schedule(schedule, phase="morning", force=False, on_date=day)
        self.assertEqual(out, schedule)

    def test_after_end_raises(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from core.schedule_guard import prepare_live_schedule

        day = date(2026, 6, 12)
        tz = ZoneInfo("Asia/Shanghai")
        schedule = [datetime(2026, 6, 12, 9, 30, tzinfo=tz), datetime(2026, 6, 12, 9, 31, tzinfo=tz)]
        fake_now = datetime(2026, 6, 12, 10, 0, tzinfo=tz)
        with (
            patch("core.schedule_guard.today_cn", return_value=day),
            patch("core.schedule_guard.datetime") as dt_mod,
        ):
            dt_mod.now.return_value = fake_now
            with self.assertRaisesRegex(RuntimeError, "上午时段已结束"):
                prepare_live_schedule(schedule, phase="morning", force=False, on_date=day)

    def test_mid_window_trims_past_points(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from core.schedule_guard import prepare_live_schedule

        day = date(2026, 6, 12)
        tz = ZoneInfo("Asia/Shanghai")
        schedule = [
            datetime(2026, 6, 12, 9, 30, tzinfo=tz),
            datetime(2026, 6, 12, 9, 31, tzinfo=tz),
            datetime(2026, 6, 12, 9, 32, tzinfo=tz),
        ]
        fake_now = datetime(2026, 6, 12, 9, 31, 0, tzinfo=tz)
        with (
            patch("core.schedule_guard.today_cn", return_value=day),
            patch("core.schedule_guard._sleep_until"),
            patch("core.schedule_guard.datetime") as dt_mod,
        ):
            dt_mod.now.side_effect = [fake_now, fake_now]
            out = prepare_live_schedule(schedule, phase="morning", force=False, on_date=day)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].strftime("%H:%M:%S"), "09:31:00")

    def test_resume_skips_collected_slots(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from core.schedule_guard import resolve_collect_schedule

        day = date(2026, 6, 11)
        tz = ZoneInfo("Asia/Shanghai")
        schedule = [
            datetime(2026, 6, 11, 9, 30, tzinfo=tz),
            datetime(2026, 6, 11, 9, 31, tzinfo=tz),
            datetime(2026, 6, 11, 9, 32, tzinfo=tz),
        ]
        existing = [
            {"captured_at": "2026-06-11 09:30:00"},
            {"captured_at": "2026-06-11 09:31:00"},
        ]
        out = resolve_collect_schedule(
            schedule,
            phase="morning",
            force=False,
            on_date=day,
            resume=True,
            existing_points=existing,
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].strftime("%H:%M:%S"), "09:32:00")

    def test_resume_by_time_not_file_length(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from core.schedule_guard import resolve_collect_schedule

        day = date(2026, 6, 11)
        tz = ZoneInfo("Asia/Shanghai")
        schedule = [
            datetime(2026, 6, 11, 9, 30, 0, tzinfo=tz),
            datetime(2026, 6, 11, 9, 31, 0, tzinfo=tz),
            datetime(2026, 6, 11, 9, 32, 0, tzinfo=tz),
            datetime(2026, 6, 11, 9, 33, 0, tzinfo=tz),
            datetime(2026, 6, 11, 9, 34, 0, tzinfo=tz),
        ]
        existing = [
            {"captured_at": "2026-06-11 09:30:00"},
            {"captured_at": "2026-06-11 09:31:00"},
        ]
        out = resolve_collect_schedule(
            schedule,
            phase="morning",
            force=False,
            on_date=day,
            resume=True,
            existing_points=existing,
        )
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0].strftime("%H:%M:%S"), "09:32:00")

    def test_require_raises_when_incomplete_and_no_slots(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from core.schedule_guard import require_collect_schedule

        day = date(2026, 6, 11)
        tz = ZoneInfo("Asia/Shanghai")
        schedule = [
            datetime(2026, 6, 11, 9, 30, tzinfo=tz),
            datetime(2026, 6, 11, 9, 31, tzinfo=tz),
        ]
        existing = [
            {"captured_at": "2026-06-11 09:30:00"},
            {"captured_at": "2026-06-11 09:31:00", "is_final": False},
        ]
        with self.assertRaisesRegex(RuntimeError, "上午段尚有未完成数据"):
            require_collect_schedule(
                schedule,
                phase="morning",
                force=False,
                on_date=day,
                resume=True,
                existing_points=existing,
                incomplete=True,
            )


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
                patch("intraday.watch.sleep_until"),
                patch("intraday.watch.is_trading_day", return_value=True),
            ):
                result = run_intraday_watch(["600519"], force=True, on_date=day, session="all")
                self.assertEqual(result["outcome"], "ok")
                self.assertEqual(result["auction_point_count"], 1)
                self.assertEqual(result["morning_point_count"], 1)
                self.assertEqual(result["afternoon_point_count"], 1)
                self.assertEqual(result["merged_point_count"], 2)
                self.assertTrue((data / f"intraday_series_{day.isoformat()}.json").is_file())
                manifest = json.loads((data / "last_intraday_watch.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["outcome"], "ok")
                self.assertEqual(manifest["phases_done"], ["auction", "morning", "afternoon"])

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
                patch("intraday.watch.sleep_until"),
                patch("intraday.watch.is_trading_day", return_value=True),
            ):
                result = run_intraday_watch(["600519"], force=True, on_date=day)
                self.assertEqual(result["outcome"], "error")
                manifest = json.loads((data / "last_intraday_watch.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["outcome"], "error")
                self.assertIn("quote down", manifest["message"])

    def test_resume_keeps_partial_morning_points(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        day = date(2026, 6, 11)
        tz = ZoneInfo("Asia/Shanghai")
        stocks = [StockItem(code="600519", name="茅台", group="我的", block_id="")]
        snap = _mock_snapshot_row("600519", "2026-06-11 09:30:00")
        short_schedule = [
            datetime(2026, 6, 11, 9, 30, tzinfo=tz),
            datetime(2026, 6, 11, 9, 31, tzinfo=tz),
            datetime(2026, 6, 11, 9, 32, tzinfo=tz),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            with patch("intraday.series.DATA_DIR", data):
                append_intraday_segment_point(
                    [{"code": "600519"}],
                    captured_at="2026-06-11 09:30:00",
                    on_date=day,
                    segment="morning",
                )
                append_intraday_segment_point(
                    [{"code": "600519"}],
                    captured_at="2026-06-11 09:31:00",
                    on_date=day,
                    segment="morning",
                )
            with (
                patch("intraday.series.DATA_DIR", data),
                patch("intraday.manifest.DATA_DIR", data),
                patch("intraday.watch.resolve_intraday_stocks", return_value=stocks),
                patch("intraday.watch.build_snapshots", return_value=[snap]),
                patch("intraday.watch._schedule_morning", return_value=(short_schedule, 60)),
                patch("intraday.watch.sleep_until"),
                patch("intraday.watch.is_trading_day", return_value=True),
            ):
                result = run_intraday_watch(["600519"], on_date=day, session="morning", resume=True)
                self.assertEqual(result["outcome"], "ok")
                loaded = load_intraday_segment(on_date=day, segment="morning")
                self.assertEqual(len(loaded), 3)
                self.assertEqual(loaded[0]["captured_at"], "2026-06-11 09:30:00")
                self.assertEqual(loaded[1]["captured_at"], "2026-06-11 09:31:00")
                self.assertEqual(loaded[2]["captured_at"], "2026-06-11 09:32:00")
                self.assertTrue(loaded[2].get("is_final"))

    def test_fresh_run_resets_partial_morning_points(self):
        day = date(2026, 6, 11)
        stocks = [StockItem(code="600519", name="茅台", group="我的", block_id="")]
        snap = _mock_snapshot_row("600519", "2026-06-11 09:30:00")
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            with patch("intraday.series.DATA_DIR", data):
                append_intraday_segment_point(
                    [{"code": "600519"}],
                    captured_at="2026-06-11 09:30:00",
                    on_date=day,
                    segment="morning",
                )
                append_intraday_segment_point(
                    [{"code": "600519"}],
                    captured_at="2026-06-11 09:31:00",
                    on_date=day,
                    segment="morning",
                )
            with (
                patch("intraday.series.DATA_DIR", data),
                patch("intraday.manifest.DATA_DIR", data),
                patch("intraday.watch.resolve_intraday_stocks", return_value=stocks),
                patch("intraday.watch.build_snapshots", return_value=[snap]),
                patch("intraday.watch.sleep_until"),
                patch("intraday.watch.is_trading_day", return_value=True),
            ):
                result = run_intraday_watch(["600519"], force=True, on_date=day, session="morning", resume=False)
                self.assertEqual(result["outcome"], "ok")
                loaded = load_intraday_segment(on_date=day, segment="morning")
                self.assertEqual(len(loaded), 1)

    def test_resume_all_skips_completed_auction(self):
        day = date(2026, 6, 11)
        stocks = [StockItem(code="600519", name="茅台", group="我的", block_id="")]
        snap = _mock_snapshot_row("600519", "2026-06-11 09:30:00")
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            with (
                patch("intraday.series.DATA_DIR", data),
                patch("intraday.manifest.DATA_DIR", data),
                patch("intraday.watch.resolve_intraday_stocks", return_value=stocks),
                patch("intraday.watch.resolve_phases", return_value=["morning"]),
                patch("intraday.watch.build_snapshots", return_value=[snap]),
                patch("intraday.watch.run_auction_watch") as mock_auction,
                patch("intraday.watch.sleep_until"),
                patch("intraday.watch.is_trading_day", return_value=True),
            ):
                result = run_intraday_watch(["600519"], force=True, on_date=day, session="all", resume=True)
                self.assertEqual(result["outcome"], "ok")
                mock_auction.assert_not_called()
                self.assertEqual(result.get("morning_point_count"), 1)


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
