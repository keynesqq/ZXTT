"""大盘资金流模块单元测试（离线）。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from market.flow_snapshot import collect_market_flow, format_flow_prompt, load_market_flow, score_flow
from market.flow_sources import fetch_market_flow, fetch_northbound, resolve_watchlist_enabled, yuan_to_yi


class YuanToYiTests(unittest.TestCase):
    def test_yuan_to_yi(self):
        self.assertEqual(yuan_to_yi(150000000), 1.5)
        self.assertIsNone(yuan_to_yi(None))


class ScoreFlowTests(unittest.TestCase):
    def test_both_strong(self):
        score, signal, hint = score_flow({"net_yi": 50.0}, {"main_net_yi": 40.0})
        self.assertEqual(signal, "强")
        self.assertGreaterEqual(score, 70)
        self.assertIn("北向", hint)

    def test_both_weak(self):
        _, signal, _ = score_flow({"net_yi": -50.0}, {"main_net_yi": -40.0})
        self.assertEqual(signal, "弱")

    def test_mixed_mid(self):
        _, signal, _ = score_flow({"net_yi": 50.0}, {"main_net_yi": -10.0})
        self.assertEqual(signal, "中")


class ResolveWatchlistTests(unittest.TestCase):
    @mock.patch("market.flow_sources.flow_cfg", return_value={"watchlist_enabled": True})
    def test_default_on(self, _cfg):
        self.assertTrue(resolve_watchlist_enabled())

    @mock.patch("market.flow_sources.flow_cfg", return_value={"watchlist_enabled": True})
    def test_cli_off(self, _cfg):
        self.assertFalse(resolve_watchlist_enabled(cli_watchlist=False))

    @mock.patch("market.flow_sources.flow_cfg", return_value={"watchlist_enabled": False})
    def test_cli_on_overrides_config(self, _cfg):
        self.assertTrue(resolve_watchlist_enabled(cli_watchlist=True))


class FetchMarketFlowTests(unittest.TestCase):
    @mock.patch("market.flow_eastmoney.fetch_market_flow_df")
    def test_live_uses_today_push2his_row(self, direct_fn):
        df = pd.DataFrame(
            [
                {
                    "日期": date(2026, 6, 9),
                    "主力净流入-净额": -10000000000.0,
                    "超大单净流入-净额": 0,
                    "大单净流入-净额": 0,
                    "中单净流入-净额": 0,
                    "小单净流入-净额": 0,
                    "主力净流入-净占比": -1.0,
                    "上证-涨跌幅": -0.5,
                    "深证-涨跌幅": -0.8,
                },
                {
                    "日期": date(2026, 6, 10),
                    "主力净流入-净额": -44680000000.0,
                    "超大单净流入-净额": 0,
                    "大单净流入-净额": 0,
                    "中单净流入-净额": 0,
                    "小单净流入-净额": 0,
                    "主力净流入-净占比": -2.5,
                    "上证-涨跌幅": -1.0,
                    "深证-涨跌幅": -2.6,
                },
            ]
        )
        direct_fn.return_value = df
        market, warnings = fetch_market_flow(trade_date=date(2026, 6, 10), live_day=True)
        self.assertEqual(market["main_net_yi"], -446.8)
        self.assertEqual(market["source_channel"], "push2his")
        self.assertEqual(warnings, [])

    @mock.patch("market.flow_sources._load_df")
    @mock.patch("market.flow_eastmoney.fetch_market_flow_df")
    def test_live_missing_today_falls_back(self, direct_fn, load_df):
        direct_fn.return_value = pd.DataFrame(
            [{"日期": date(2026, 6, 9), "主力净流入-净额": -10000000000.0, "主力净流入-净占比": -1.0}]
        )
        load_df.return_value = (direct_fn.return_value, [])
        market, warnings = fetch_market_flow(trade_date=date(2026, 6, 10), live_day=True)
        self.assertEqual(market["main_net_yi"], -100.0)
        self.assertTrue(any("无 2026-06-10 当日行" in w for w in warnings))


class FetchNorthboundTests(unittest.TestCase):
    @mock.patch("market.flow_eastmoney.fetch_hsgt_summary_df")
    def test_live_summary_parses_sh_sz(self, direct_fn):
        df = pd.DataFrame(
            [
                {
                    "交易日": date(2026, 6, 10),
                    "类型": "沪港通",
                    "资金方向": "北向",
                    "交易状态": 1,
                    "成交净买额": 10.5,
                    "资金净流入": 9.0,
                },
                {
                    "交易日": date(2026, 6, 10),
                    "类型": "深港通",
                    "资金方向": "北向",
                    "交易状态": 1,
                    "成交净买额": 20.0,
                    "资金净流入": 18.0,
                },
            ]
        )
        direct_fn.return_value = df
        north, warnings = fetch_northbound(trade_date=date(2026, 6, 10), live_day=True)
        self.assertEqual(north["net_yi"], 30.5)
        self.assertEqual(north["sh_connect_net_yi"], 10.5)
        self.assertEqual(north["sz_connect_net_yi"], 20.0)
        self.assertEqual(warnings, [])


class CollectMarketFlowTests(unittest.TestCase):
    def _body(self, *, watchlist_enabled: bool = True) -> dict:
        return {
            "collected_at": 1.0,
            "collected_at_iso": "2026-06-10 22:00:00",
            "watchlist_enabled": watchlist_enabled,
            "northbound": {"net_yi": 12.0, "sh_connect_net_yi": 5.0, "sz_connect_net_yi": 7.0},
            "market": {"main_net_yi": -8.0},
            "sectors_inflow_top": [{"name": "电子", "main_net_yi": 50.0}],
            "sectors_outflow_top": [{"name": "医药", "main_net_yi": -20.0}],
            "watchlist_flow": [{"code": "600519", "name": "贵州茅台", "main_net_yi": 1.2}]
            if watchlist_enabled
            else [],
            "flow_score": 55,
            "flow_signal": "中",
            "flow_hint": "test",
            "warnings": [],
        }

    def test_collect_writes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp) / "market_flow"
            with mock.patch("market.flow_snapshot._STORAGE", storage), mock.patch(
                "market.flow_snapshot._collect_layers",
                return_value=(self._body(), []),
            ), mock.patch("core.trading_calendar.market_data_date", return_value=date(2026, 6, 10)), mock.patch(
                "market.flow_snapshot.flow_cfg", return_value={"enabled": True}
            ):
                data = collect_market_flow(calendar_date=date(2026, 6, 10), slot="evening")
                self.assertEqual(data["northbound"]["net_yi"], 12.0)
                path = storage / "2026-06-10.json"
                self.assertTrue(path.is_file())
                loaded = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(loaded["latest_slot"], "evening")

    def test_no_watchlist_empty_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp) / "market_flow"
            with mock.patch("market.flow_snapshot._STORAGE", storage), mock.patch(
                "market.flow_snapshot._collect_layers",
                return_value=(self._body(watchlist_enabled=False), []),
            ), mock.patch("core.trading_calendar.market_data_date", return_value=date(2026, 6, 10)), mock.patch(
                "market.flow_snapshot.flow_cfg", return_value={"enabled": True}
            ):
                data = collect_market_flow(
                    calendar_date=date(2026, 6, 10),
                    slot="evening",
                    watchlist_enabled=False,
                )
                self.assertFalse(data["watchlist_enabled"])
                self.assertEqual(data["watchlist_flow"], [])

    def test_merge_slots(self):
        body = self._body()
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp) / "market_flow"
            with mock.patch("market.flow_snapshot._STORAGE", storage), mock.patch(
                "market.flow_snapshot._collect_layers",
                return_value=(body, []),
            ), mock.patch("core.trading_calendar.market_data_date", return_value=date(2026, 6, 10)), mock.patch(
                "market.flow_snapshot.flow_cfg", return_value={"enabled": True}
            ):
                collect_market_flow(calendar_date=date(2026, 6, 10), slot="midday")
                collect_market_flow(calendar_date=date(2026, 6, 10), slot="evening")
                loaded = load_market_flow(date(2026, 6, 10))
                self.assertIsNotNone(loaded)
                slots = [s["slot"] for s in loaded["snapshots"]]
                self.assertEqual(slots, ["midday", "evening"])


class FormatFlowPromptTests(unittest.TestCase):
    def test_prompt_contains_core_lines(self):
        data = {
            "trade_date": "2026-06-10",
            "collected_at_iso": "2026-06-10 22:00:00",
            "latest_slot": "evening",
            "flow_signal": "中",
            "northbound": {"net_yi": 12.0, "sh_connect_net_yi": 5.0, "sz_connect_net_yi": 7.0},
            "market": {"main_net_yi": -8.0},
            "sectors_inflow_top": [{"name": "电子", "main_net_yi": 50.0}],
            "watchlist_flow": [{"name": "贵州茅台", "main_net_yi": 1.2}],
        }
        text = "\n".join(format_flow_prompt(data))
        self.assertIn("北向成交净买额", text)
        self.assertIn("大盘主力净流入", text)
        self.assertIn("电子", text)


if __name__ == "__main__":
    unittest.main()
