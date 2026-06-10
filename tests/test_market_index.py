"""指数快照模块单元测试（离线）。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from market.index_snapshot import collect_market_index, format_index_prompt, load_market_index
from quote.tencent import _parse_index_line, fetch_index_open_gaps, fetch_index_snapshots


_SAMPLE_LINE = (
    "v_sh000001=\"1~上证指数~000001~3986.66~4010.03~3985.12~383660494~0~0~0.00~0~0.00~0~0.00~0~"
    "0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~~20260610120500~-23.37~-0.58~"
    "4006.31~3972.87~3986.66/383660494/807012256512~383660494~80701226~0.80~17.66~~4006.31~"
    "3972.87~0.83~616415.11~664575.74~0.00~-1~-1~1.19~0~3992.66~~~~~~80701225.6512~0.0000~0~ ~ZS~"
    "0.45~-2.38~~~~4258.86~3347.65~-2.62~-6.03~-3.45~4818525019939~~9.73~4.57~4818525019939~~~"
    "17.78~0.19~~CNY~0~~0.00~0~\""
)


class ParseIndexLineTests(unittest.TestCase):
    def test_parse_index_fields(self):
        row = _parse_index_line(_SAMPLE_LINE, "sh000001", "上证指数")
        self.assertIsNotNone(row)
        self.assertEqual(row["symbol"], "sh000001")
        self.assertEqual(row["price"], 3986.66)
        self.assertEqual(row["pct_chg"], -0.58)
        self.assertEqual(row["change"], -23.37)
        self.assertEqual(row["volume"], 383660494.0)
        self.assertEqual(row["snapshot_at"], "2026-06-10 12:05:00")
        self.assertIsNotNone(row["open_gap_pct"])


class CollectMarketIndexTests(unittest.TestCase):
    def test_collect_writes_snapshots(self):
        sample = [
            {
                "symbol": "sh000001",
                "market": "sh",
                "code": "000001",
                "name": "上证指数",
                "price": 3986.66,
                "pct_chg": -0.58,
                "open_gap_pct": -0.1,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp) / "market_index"
            with mock.patch("market.index_snapshot._STORAGE", storage), mock.patch(
                "market.index_snapshot.fetch_index_snapshots", return_value=sample
            ), mock.patch("collect.manifest.track_source"), mock.patch(
                "collect.manifest.record_source"
            ), mock.patch(
                "core.trading_calendar.market_data_date", return_value=date(2026, 6, 9)
            ):
                data = collect_market_index(calendar_date=date(2026, 6, 9), slot="evening")
                self.assertEqual(len(data["indices"]), 1)
                path = storage / "2026-06-09.json"
                self.assertTrue(path.is_file())
                loaded = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(loaded["latest_slot"], "evening")
                self.assertEqual(len(loaded["snapshots"]), 1)

    def test_merge_multiple_slots(self):
        sample = [
            {
                "symbol": "sh000001",
                "name": "上证指数",
                "price": 4000.0,
                "pct_chg": 1.0,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp) / "market_index"
            with mock.patch("market.index_snapshot._STORAGE", storage), mock.patch(
                "market.index_snapshot.fetch_index_snapshots", return_value=sample
            ), mock.patch("collect.manifest.track_source"), mock.patch(
                "collect.manifest.record_source"
            ), mock.patch(
                "core.trading_calendar.market_data_date", return_value=date(2026, 6, 9)
            ):
                collect_market_index(calendar_date=date(2026, 6, 9), slot="morning")
                collect_market_index(calendar_date=date(2026, 6, 9), slot="evening")
                loaded = load_market_index(date(2026, 6, 9))
                self.assertIsNotNone(loaded)
                slots = [s["slot"] for s in loaded["snapshots"]]
                self.assertEqual(slots, ["morning", "evening"])


class FormatIndexPromptTests(unittest.TestCase):
    def test_prompt_includes_volume_fields(self):
        data = {
            "trade_date": "2026-06-10",
            "collected_at_iso": "2026-06-10 12:00:00",
            "latest_slot": "evening",
            "indices": [
                {
                    "name": "上证指数",
                    "price": 3986.66,
                    "pct_chg": -0.58,
                    "change": -23.37,
                    "open_gap_pct": -0.62,
                    "amplitude": 0.83,
                    "amount_yi": 8070.12,
                    "pct_ytd": -2.62,
                    "snapshot_at": "2026-06-10 12:05:00",
                }
            ],
        }
        text = "\n".join(format_index_prompt(data))
        self.assertIn("涨跌 -23.37 点", text)
        self.assertIn("成交额 8070.12 亿", text)
        self.assertIn("年初至今 -2.62%", text)


class FetchIndexOpenGapsTests(unittest.TestCase):
    def test_open_gaps_from_snapshots(self):
        with mock.patch(
            "quote.tencent.fetch_index_snapshots",
            return_value=[
                {
                    "symbol": "sh000001",
                    "name": "上证指数",
                    "price": 4000.0,
                    "open": 3990.0,
                    "pre_close": 3980.0,
                    "pct_chg": 0.5,
                    "open_gap_pct": 0.25,
                }
            ],
        ):
            gaps = fetch_index_open_gaps()
            self.assertEqual(len(gaps), 1)
            self.assertEqual(gaps[0]["open_gap_pct"], 0.25)
