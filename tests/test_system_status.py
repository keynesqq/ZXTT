"""系统状态仪表盘聚合。"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from report.hub import aggregate_hub
from report.hub_html import build_hub_page
from report.system_status import aggregate_system_status


class TestSystemStatus(unittest.TestCase):
    def test_hub_includes_services(self) -> None:
        hub = aggregate_hub(date(2026, 6, 12))
        self.assertIn("services", hub)
        self.assertEqual(hub["schema_version"], 2)
        svc = hub["services"]
        self.assertIn("overall", svc)
        self.assertIn("groups", svc)
        ids = [g["id"] for g in svc["groups"]]
        self.assertEqual(ids, ["live", "market", "feeds", "reports"])

    def test_intraday_covers_auction(self) -> None:
        svc = aggregate_system_status(date(2026, 6, 12), aggregate_hub(date(2026, 6, 12))["slots"])
        live = next(g for g in svc["groups"] if g["id"] == "live")
        self.assertEqual(len(live["items"]), 1)
        self.assertEqual(live["items"][0]["id"], "intraday")
        self.assertEqual(live["items"][0]["label"], "全天监控")
        svc = aggregate_system_status(date(2026, 6, 12), aggregate_hub(date(2026, 6, 12))["slots"])
        market = next(g for g in svc["groups"] if g["id"] == "market")
        quote = next(it for it in market["items"] if it["id"] == "quote_query")
        self.assertEqual(quote["status"], "ok")
        feeds = next(g for g in svc["groups"] if g["id"] == "feeds")
        cls_art = next(it for it in feeds["items"] if it["id"] == "cls_articles")
        self.assertEqual(cls_art["status"], "warn")

    def test_hub_page_has_dashboard(self) -> None:
        page = build_hub_page(aggregate_hub(date(2026, 6, 12)))
        self.assertIn("status-dash", page)
        self.assertIn("系统状态", page)
        self.assertIn("全天监控", page)
        self.assertNotIn("盘中分钟线", page)
        self.assertIn("行情数据", page)
        self.assertIn("资讯公告", page)
        self.assertIn("renderServices", page)
        self.assertIn("pollHubViaScript", page)
        self.assertIn("hubRevision", page)


if __name__ == "__main__":
    unittest.main()
