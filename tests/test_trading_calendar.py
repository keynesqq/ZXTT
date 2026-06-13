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
from core.trading_calendar import is_trading_day, verify_exchange_calendar


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


if __name__ == "__main__":
    unittest.main()
