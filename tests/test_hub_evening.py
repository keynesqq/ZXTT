"""Hub 四卡：昨收 / 开盘 / 午间 / 晚间收盘。"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from report.hub import aggregate_hub, refresh_hub_feed


class TestHubEveningServeDay(unittest.TestCase):
    def test_four_slots_on_trading_day(self) -> None:
        hub = aggregate_hub(date(2026, 6, 12))
        slots = hub["slots"]
        self.assertIn("evening_prev", slots)
        self.assertIn("morning", slots)
        self.assertIn("midday", slots)
        self.assertIn("evening", slots)

    def test_yesterday_evening_card(self) -> None:
        hub = aggregate_hub(date(2026, 6, 12))
        prev = hub["slots"]["evening_prev"]
        self.assertEqual(prev["label"], "昨日作战卡")
        self.assertTrue(prev["report_ready"])
        self.assertEqual(prev["report_href"], "2026-06-11/daily_evening.html")
        self.assertEqual(prev["report_trade_date"], "2026-06-11")
        self.assertEqual(prev["status"], "ok")

    def test_today_evening_close_card(self) -> None:
        hub = aggregate_hub(date(2026, 6, 12))
        close = hub["slots"]["evening"]
        self.assertEqual(close["label"], "晚间收盘卡")
        self.assertTrue(close["report_ready"])
        self.assertEqual(close["report_href"], "2026-06-12/daily_evening.html")
        self.assertEqual(close["report_trade_date"], "2026-06-12")
        self.assertEqual(close["status"], "ok")

    def test_hub_page_accordion_list(self) -> None:
        from report.hub_html import build_hub_page

        page = build_hub_page(aggregate_hub(date(2026, 6, 12)))
        self.assertIn("report-list", page)
        self.assertIn("<details>", page)
        self.assertIn("report-embed", page)
        self.assertIn("hub-templates", page)
        self.assertNotIn("report-frame", page)
        self.assertNotIn("<iframe", page)
        self.assertIn("昨日作战卡", page)
        self.assertIn("晚间收盘卡", page)
        self.assertNotIn('class="grid"', page)
        self.assertNotIn("report-link", page)

    def test_non_trading_day_shows_last_trade_date(self) -> None:
        from report.hub import _hub_view_day, publish_hub

        self.assertEqual(_hub_view_day(date(2026, 6, 13)), date(2026, 6, 12))
        path = publish_hub(date(2026, 6, 13))
        self.assertEqual(path.name, "2026-06-12.json")
        hub = aggregate_hub(date(2026, 6, 12))
        self.assertEqual(hub["trade_date"], "2026-06-12")
        self.assertTrue(hub["slots"]["evening"]["report_ready"])

    def test_publish_hub_bakes_templates(self) -> None:
        from report.hub import publish_hub

        publish_hub(date(2026, 6, 12))
        page = (ROOT / "reports" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="tpl-evening"', page)
        self.assertIn('id="tpl-evening_prev"', page)
        hub = json.loads(
            (ROOT / "data" / "report_hub" / "2026-06-12.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("templates", hub)
        self.assertIn("evening", hub["slots"])
        js = (ROOT / "reports" / "hub_status.js").read_text(encoding="utf-8")
        self.assertNotIn('"templates"', js)

    def test_hub_page_no_templates_in_boot(self) -> None:
        from report.hub import publish_hub

        publish_hub(date(2026, 6, 12))
        page = (ROOT / "reports" / "index.html").read_text(encoding="utf-8")
        boot_raw = page.split("window.__HUB_BOOT__=", 1)[1].split(";</script>", 1)[0]
        boot = json.loads(boot_raw)
        self.assertNotIn("templates", boot)
        self.assertIn("slots", boot)

    def test_refresh_hub_feed_writes_js_without_index(self) -> None:
        from report.hub import publish_hub

        publish_hub(date(2026, 6, 12))
        index_before = (ROOT / "reports" / "index.html").read_text(encoding="utf-8")
        json_path = ROOT / "data" / "report_hub" / "2026-06-12.json"
        json_before = json.loads(json_path.read_text(encoding="utf-8"))
        with patch("report.hub.now_iso", return_value="2099-01-01 00:00:00"), patch(
            "report.system_status.now_iso", return_value="2099-01-01 00:00:00"
        ), patch("report.hub._FEED_MIN_INTERVAL_SEC", 0.0):
            path = refresh_hub_feed(date(2026, 6, 12), force=True)
        self.assertIsNotNone(path)
        json_after = json.loads(json_path.read_text(encoding="utf-8"))
        index_after = (ROOT / "reports" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(json_after["updated_at"], "2099-01-01 00:00:00")
        self.assertNotEqual(json_before["updated_at"], json_after["updated_at"])
        self.assertEqual(index_before, index_after)


if __name__ == "__main__":
    unittest.main()
