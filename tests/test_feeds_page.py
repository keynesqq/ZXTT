"""公告资讯页。"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from report.feeds_data import load_feeds_page_context
from report.feeds_html import build_feeds_page
from report.hub import publish_feeds, publish_hub
from report.web_common import web_topbar


class TestFeedsPage(unittest.TestCase):
    def test_topbar_links(self) -> None:
        nav = web_topbar(active="feeds", trade_date="2026-06-12")
        self.assertIn("feeds.html?date=2026-06-12", nav)
        self.assertIn('class="active"', nav)
        self.assertIn("公告资讯", nav)

    def test_build_page_structure(self) -> None:
        ctx = {
            "trade_date": "2026-06-12",
            "stock_count": 1,
            "item_count": 2,
            "feeds_missing": False,
            "ann_lookback_days": 3,
            "news_lookback_days": 7,
            "ann_updated_at": "2026-06-12 22:00:15",
            "news_updated_at": "2026-06-12 22:00:29",
            "feeds_group_order": ["我的"],
            "categories": ["公告", "研报", "资讯", "观点", "行业资讯"],
            "groups": {
                "我的": [
                    {
                        "code": "600519",
                        "name": "贵州茅台",
                        "industry": "白酒",
                        "warnings": ["资讯：近7日无数据"],
                        "queried_at": "2026-06-12 22:00:00",
                        "categories": {
                            "公告": [
                                {
                                    "title": "测试公告",
                                    "pub_date": "2026-06-12",
                                    "pub_time": "",
                                    "url": "http://example.com/a.pdf",
                                    "source": "巨潮",
                                }
                            ],
                            "研报": [],
                            "资讯": [
                                {
                                    "title": "测试资讯",
                                    "pub_date": "2026-06-11",
                                    "pub_time": "10:00",
                                    "url": "",
                                    "source": "东财",
                                }
                            ],
                            "观点": [],
                            "行业资讯": [],
                        },
                    }
                ]
            },
            "watchlist_source": {"watchlist_groups": ["我的"], "watchlist_stock_count": 1},
        }
        page = build_feeds_page(ctx)
        self.assertIn("feeds-scope", page)
        self.assertIn("公告资讯", page)
        self.assertIn("600519", page)
        self.assertIn("测试公告", page)
        self.assertIn("测试资讯", page)
        self.assertIn("snap-group-btn", page)

    @patch("report.feeds_data.load_snapshot_page_context")
    def test_load_context_from_cache(self, load_snap) -> None:
        load_snap.return_value = {
            "trade_date": "2026-06-12",
            "snapshot_groups": ["我的"],
            "rows": [
                {"code": "600519", "name": "贵州茅台", "group": "我的", "industry": "白酒"},
            ],
            "watchlist_source": {},
        }
        ctx = load_feeds_page_context(date(2026, 6, 12))
        self.assertEqual(ctx["trade_date"], "2026-06-12")
        self.assertGreaterEqual(ctx["stock_count"], 1)
        self.assertIn("我的", ctx["groups"])

    def test_publish_feeds_writes_html(self) -> None:
        publish_feeds(date(2026, 6, 12))
        feeds = ROOT / "reports" / "feeds.html"
        self.assertTrue(feeds.is_file())
        text = feeds.read_text(encoding="utf-8")
        self.assertIn("feeds-scope", text)
        self.assertIn("web-topnav", text)

    def test_publish_hub_writes_feeds(self) -> None:
        publish_hub(date(2026, 6, 12))
        feeds = ROOT / "reports" / "feeds.html"
        self.assertTrue(feeds.is_file())
        index = (ROOT / "reports" / "index.html").read_text(encoding="utf-8")
        self.assertIn("feeds.html", index)

    def test_publish_settings_writes_html(self) -> None:
        from report.hub import publish_settings

        publish_settings(date(2026, 6, 12))
        settings = ROOT / "reports" / "settings.html"
        self.assertTrue(settings.is_file())
        text = settings.read_text(encoding="utf-8")
        self.assertIn("settings-panel-schedule", text)
        self.assertIn("settings.html", text)  # topnav relative link


if __name__ == "__main__":
    unittest.main()
