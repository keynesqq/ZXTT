"""feeds 指纹复用逻辑单测。"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from evening.feeds_fingerprint import decide_feeds_status, fingerprint_feeds

_FEEDS = {
    "公告": [{"title": "公告A", "pub_date": "2026-06-10"}],
    "资讯": [],
    "观点": [],
    "研报": [],
    "行业资讯": [],
}


class DecideFeedsStatusTests(unittest.TestCase):
    def test_first_run_when_no_baseline(self) -> None:
        fp = fingerprint_feeds(_FEEDS)
        status, _, _ = decide_feeds_status(
            "600519",
            _FEEDS,
            trade_date=date(2026, 6, 10),
            today_baseline=None,
            prev_baseline=None,
        )
        self.assertEqual(status, "first_run")
        self.assertTrue(fp)

    def test_same_day_reuse_without_prev(self) -> None:
        fp = fingerprint_feeds(_FEEDS)
        today_bl = {"codes": {"600519": {"fingerprint": fp}}}
        status, _, _ = decide_feeds_status(
            "600519",
            _FEEDS,
            trade_date=date(2026, 6, 10),
            today_baseline=today_bl,
            prev_baseline=None,
        )
        self.assertEqual(status, "reuse")

    def test_new_code_reuse_from_today_baseline(self) -> None:
        fp = fingerprint_feeds(_FEEDS)
        prev_bl = {"codes": {"000001": {"fingerprint": "other"}}}
        today_bl = {"codes": {"600519": {"fingerprint": fp}}}
        status, _, _ = decide_feeds_status(
            "600519",
            _FEEDS,
            trade_date=date(2026, 6, 10),
            today_baseline=today_bl,
            prev_baseline=prev_bl,
        )
        self.assertEqual(status, "reuse")

    def test_refresh_when_fingerprint_changed(self) -> None:
        fp = fingerprint_feeds(_FEEDS)
        prev_bl = {"codes": {"600519": {"fingerprint": "stale"}}}
        status, _, _ = decide_feeds_status(
            "600519",
            _FEEDS,
            trade_date=date(2026, 6, 10),
            today_baseline=None,
            prev_baseline=prev_bl,
        )
        self.assertEqual(status, "refresh")

    def test_refresh_when_today_fingerprint_differs(self) -> None:
        feeds2 = {
            **_FEEDS,
            "资讯": [{"title": "新资讯", "pub_date": "2026-06-10"}],
        }
        fp2 = fingerprint_feeds(feeds2)
        today_bl = {"codes": {"600519": {"fingerprint": fingerprint_feeds(_FEEDS)}}}
        status, _, _ = decide_feeds_status(
            "600519",
            feeds2,
            trade_date=date(2026, 6, 10),
            today_baseline=today_bl,
            prev_baseline={"codes": {"600519": {"fingerprint": fingerprint_feeds(_FEEDS)}}},
        )
        self.assertEqual(status, "refresh")
        self.assertTrue(fp2)


if __name__ == "__main__":
    unittest.main()
