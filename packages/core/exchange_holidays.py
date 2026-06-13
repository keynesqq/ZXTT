"""沪深北交易所公告休市日（2026 年据证监办发〔2025〕130 号及三所 2025-12-22 通知）。"""
from __future__ import annotations

from datetime import date, timedelta

# 各年 (start, end) 闭区间；区间含周末，A 股不因国务院调休在周六日开市
_EXCHANGE_CLOSURE_RANGES: dict[int, tuple[tuple[date, date], ...]] = {
    2026: (
        (date(2026, 1, 1), date(2026, 1, 3)),  # 元旦
        (date(2026, 2, 15), date(2026, 2, 23)),  # 春节
        (date(2026, 4, 4), date(2026, 4, 6)),  # 清明节
        (date(2026, 5, 1), date(2026, 5, 5)),  # 劳动节
        (date(2026, 6, 19), date(2026, 6, 21)),  # 端午节
        (date(2026, 9, 25), date(2026, 9, 27)),  # 中秋节
        (date(2026, 10, 1), date(2026, 10, 7)),  # 国庆节
    ),
}


def closure_ranges_for_year(year: int) -> tuple[tuple[date, date], ...]:
    return _EXCHANGE_CLOSURE_RANGES.get(year, ())


def exchange_closed_on(d: date) -> bool:
    """交易所公告休市或固定周末休市。"""
    if d.weekday() >= 5:
        return True
    for start, end in closure_ranges_for_year(d.year):
        if start <= d <= end:
            return True
    return False


def is_trading_day_exchange_standard(d: date) -> bool:
    """周一至周五，除交易所公告休市日；周六日固定休市（含调休上班日）。"""
    return not exchange_closed_on(d)


def trading_days_in_year(year: int) -> set[date]:
    out: set[date] = set()
    d = date(year, 1, 1)
    end = date(year, 12, 31)
    while d <= end:
        if is_trading_day_exchange_standard(d):
            out.add(d)
        d += timedelta(days=1)
    return out


def verify_against_calendar(calendar: set[date], *, year: int) -> dict:
    """对照交易所标准与外部日历（如 akshare）。"""
    mismatches: list[dict] = []
    d = date(year, 1, 1)
    end = date(year, 12, 31)
    while d <= end:
        std = is_trading_day_exchange_standard(d)
        ext = d in calendar
        if std != ext:
            mismatches.append(
                {
                    "date": d.isoformat(),
                    "exchange_standard": std,
                    "external": ext,
                }
            )
        d += timedelta(days=1)
    return {
        "year": year,
        "ok": not mismatches,
        "exchange_trading_days": len(trading_days_in_year(year)),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }
