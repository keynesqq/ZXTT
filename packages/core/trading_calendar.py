from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from core.exchange_holidays import (
    is_trading_day_exchange_standard,
    verify_against_calendar,
)

_CN_TZ = ZoneInfo("Asia/Shanghai")

_calendar: set[date] | None = None
_calendar_fallback = False
_calendar_source = "unknown"


def _load_calendar() -> set[date]:
    global _calendar, _calendar_fallback, _calendar_source
    if _calendar is not None:
        return _calendar
    try:
        from akshare.tool.trade_date_hist import tool_trade_date_hist_sina

        df = tool_trade_date_hist_sina()
        _calendar = set(df["trade_date"].tolist())
        if not _calendar:
            raise RuntimeError("empty calendar")
        _calendar_source = "akshare"
    except Exception:
        _calendar = set()
        _calendar_fallback = True
        _calendar_source = "exchange_standard"
    return _calendar


def calendar_using_fallback() -> bool:
    _load_calendar()
    return _calendar_fallback


def calendar_source() -> str:
    _load_calendar()
    return _calendar_source


def verify_exchange_calendar(*, year: int = 2026) -> dict:
    """对照沪深北交易所休市标准与当前加载的 akshare 日历。"""
    cal = _load_calendar()
    if not cal:
        return {
            "year": year,
            "ok": True,
            "source": calendar_source(),
            "note": "akshare 不可用，已降级为交易所标准",
            "mismatch_count": 0,
            "mismatches": [],
        }
    result = verify_against_calendar(cal, year=year)
    result["source"] = calendar_source()
    return result


def today_cn() -> date:
    return datetime.now(_CN_TZ).date()


def is_trading_day(d: date) -> bool:
    cal = _load_calendar()
    if cal:
        return d in cal
    return is_trading_day_exchange_standard(d)


def next_trading_day(d: date, *, max_scan: int = 10) -> date | None:
    for i in range(1, max_scan + 1):
        candidate = d + timedelta(days=i)
        if is_trading_day(candidate):
            return candidate
    return None


def previous_trading_day(d: date, *, max_scan: int = 10) -> date | None:
    """d 之前最近的一个 A 股交易日（不含 d 本身）。"""
    for i in range(1, max_scan + 1):
        candidate = d - timedelta(days=i)
        if is_trading_day(candidate):
            return candidate
    return None


def market_data_date(calendar_date: date | None = None) -> date:
    """AkShare/财联社等「已收盘行情」应对齐的交易日。"""
    d = calendar_date or today_cn()
    if is_trading_day(d):
        return d
    prev = previous_trading_day(d)
    return prev if prev else d


def should_run_evening(on_date: date) -> bool:
    """22:00：「明天」是交易日（用于交易日前夜资讯任务门禁）。"""
    tomorrow = on_date + timedelta(days=1)
    return is_trading_day(tomorrow)


def should_run_eve_news(on_date: date) -> bool:
    """交易日前夜资讯：今日非交易日且明日是交易日（周日晚、长假最后一晚等）。"""
    return should_run_evening(on_date) and not is_trading_day(on_date)


def should_run_intraday(on_date: date) -> bool:
    """盘前 / 午间：当天是交易日。"""
    return is_trading_day(on_date)


def _slot_schedule_key(slot: str, phase: str | None = None) -> str:
    if slot == "morning" and phase:
        return f"morning_{phase}"
    if slot == "midday" and phase:
        return f"midday_{phase}"
    return slot


def slot_time_reached(
    slot: str,
    phase: str | None = None,
    *,
    on_date: date | None = None,
    now: datetime | None = None,
) -> bool:
    """是否已到 config.schedule.slots 中该档位的计划时刻。"""
    from datetime import time

    from core.config import load_config

    dt = now or datetime.now(_CN_TZ)
    d = on_date or dt.date()
    if d != dt.date():
        return True
    cfg = load_config()
    slots = (cfg.get("schedule") or {}).get("slots") or {}
    key = _slot_schedule_key(slot, phase)
    slot_cfg = slots.get(key) or {}
    t_str = str(slot_cfg.get("time") or ("12:50" if slot == "midday" else "09:00"))
    parts = t_str.strip().split(":")
    h, m = int(parts[0]), int(parts[1])
    sec = int(parts[2]) if len(parts) >= 3 else 0
    return dt.time() >= time(h, m, sec)


def format_date_cn(d: date) -> str:
    return f"{d.year}年{d.month}月{d.day}日"


def trading_day_info(on_date: date | None = None, *, max_scan: int = 30) -> dict:
    """供展示：今日是否交易日、下一交易日与粗粒度天数差。"""
    d = on_date or today_cn()
    trading = is_trading_day(d)
    nxt = next_trading_day(d, max_scan=max_scan)
    days_left = (nxt - d).days if nxt else 0
    return {
        "today_cn": format_date_cn(d),
        "is_trading_day": trading,
        "today_status": "交易日" if trading else "非交易日",
        "next_trading_day_cn": format_date_cn(nxt) if nxt else "—",
        "days_until_next": days_left,
        "days_until_label": f"还有 {days_left} 天" if nxt and days_left > 0 else "",
    }
