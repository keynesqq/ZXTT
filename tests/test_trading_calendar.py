from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from core.exchange_holidays import (
    exchange_closed_on,
    is_trading_day_exchange_standard,
    trading_days_in_year,
    verify_against_calendar,
)
from core.trading_calendar import is_trading_day, should_run_evening, should_run_eve_news, verify_exchange_calendar


class TestExchangeHolidays2026(unittest.TestCase):
    def test_weekend_always_closed(self) -> None:
        self.assertTrue(exchange_closed_on(date(2026, 1, 4)))  # 周日，公告周末休市
        self.assertTrue(exchange_closed_on(date(2026, 2, 14)))  # 周六调休上班，A 股仍休

    def test_holiday_weekdays_closed(self) -> None:
        self.assertFalse(is_trading_day_exchange_standard(date(2026, 1, 1)))
        self.assertFalse(is_trading_day_exchange_standard(date(2026, 2, 17)))
        self.assertFalse(is_trading_day_exchange_standard(date(2026, 10, 1)))

    def test_normal_weekday_open(self) -> None:
        self.assertTrue(is_trading_day_exchange_standard(date(2026, 6, 12)))
        self.assertTrue(is_trading_day_exchange_standard(date(2026, 1, 5)))

    def test_2026_trading_day_count(self) -> None:
        self.assertEqual(len(trading_days_in_year(2026)), 242)


class TestTradingCalendarFallback(unittest.TestCase):
    def test_fallback_uses_exchange_standard(self) -> None:
        with mock.patch("core.trading_calendar._calendar", set()), mock.patch(
            "core.trading_calendar._calendar_fallback", True
        ):
            self.assertFalse(is_trading_day(date(2026, 1, 1)))
            self.assertTrue(is_trading_day(date(2026, 6, 12)))

    def test_verify_matches_exchange_when_akshare_ok(self) -> None:
        result = verify_exchange_calendar(year=2026)
        self.assertTrue(result["ok"], result.get("mismatches"))

    def test_verify_detects_mismatch(self) -> None:
        bad = trading_days_in_year(2026)
        bad.add(date(2026, 1, 1))
        report = verify_against_calendar(bad, year=2026)
        self.assertFalse(report["ok"])
        self.assertGreater(report["mismatch_count"], 0)


class TestShouldRunEvening(unittest.TestCase):
    def test_friday_evening_skips(self) -> None:
        self.assertFalse(should_run_evening(date(2026, 6, 5)))

    def test_saturday_evening_skips(self) -> None:
        self.assertFalse(should_run_evening(date(2026, 6, 6)))

    def test_sunday_evening_runs_for_monday(self) -> None:
        self.assertTrue(should_run_evening(date(2026, 6, 7)))

    def test_monday_evening_runs(self) -> None:
        self.assertTrue(should_run_evening(date(2026, 6, 8)))

    def test_holiday_eve_runs_when_tomorrow_opens(self) -> None:
        # 2026 春节 2/15-2/23 休市，2/24 恢复交易
        self.assertFalse(is_trading_day_exchange_standard(date(2026, 2, 23)))
        self.assertTrue(should_run_evening(date(2026, 2, 23)))


class TestShouldRunEveNews(unittest.TestCase):
    def test_trading_day_evening_not_eve_news(self) -> None:
        self.assertTrue(is_trading_day_exchange_standard(date(2026, 6, 8)))
        self.assertFalse(should_run_eve_news(date(2026, 6, 8)))

    def test_sunday_eve_news_for_monday(self) -> None:
        self.assertTrue(should_run_eve_news(date(2026, 6, 7)))

    def test_friday_not_eve_news(self) -> None:
        self.assertFalse(should_run_eve_news(date(2026, 6, 5)))

    def test_holiday_last_night(self) -> None:
        self.assertTrue(should_run_eve_news(date(2026, 2, 23)))


if __name__ == "__main__":
    unittest.main()
