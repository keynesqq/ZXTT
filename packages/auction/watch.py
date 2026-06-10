"""集合竞价走势：按用户提供的个股列表，9:15–9:25 每 30 秒采一次，最后汇总走势。"""
from __future__ import annotations

import time
from datetime import date, datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo

from auction.manifest import save_watch_manifest
from auction.series import append_auction_series_point, load_auction_series, reset_auction_series
from auction.stocks import resolve_auction_stocks
from auction.trajectory import write_auction_trend
from core.config import auction_cfg
from core.trading_calendar import is_trading_day, today_cn
from quote.auction_snap import build_auction_snapshots

_CN_TZ = ZoneInfo("Asia/Shanghai")


def _parse_hms(raw: str, default: dt_time) -> dt_time:
    parts = str(raw or "").strip().split(":")
    if len(parts) < 2:
        return default
    try:
        h, m = int(parts[0]), int(parts[1])
        s = int(parts[2]) if len(parts) >= 3 else 0
        return dt_time(h, m, s)
    except ValueError:
        return default


def _schedule_times(on_date: date) -> tuple[list[datetime], int]:
    cfg = auction_cfg()
    start_t = _parse_hms(str(cfg.get("watch_start") or "09:15:05"), dt_time(9, 15, 5))
    end_t = _parse_hms(str(cfg.get("watch_end") or "09:25:05"), dt_time(9, 25, 5))
    interval = max(1, int(cfg.get("interval_sec") or 30))
    start = datetime.combine(on_date, start_t, tzinfo=_CN_TZ)
    end = datetime.combine(on_date, end_t, tzinfo=_CN_TZ)
    times: list[datetime] = []
    t = start
    while t <= end:
        times.append(t)
        t = t + timedelta(seconds=interval)
    if not times or times[-1] != end:
        times.append(end)
    dedup: list[datetime] = []
    seen: set[str] = set()
    for item in times:
        key = item.strftime("%H:%M:%S")
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)
    return dedup, interval


def _sleep_until(target: datetime) -> None:
    now = datetime.now(_CN_TZ)
    sec = (target - now).total_seconds()
    if sec > 0:
        time.sleep(sec)


def run_auction_watch(
    codes: list[str],
    *,
    force: bool = False,
    on_date: date | None = None,
) -> dict:
    """采集集合竞价走势；codes 为必填个股列表（一只或多只）。"""
    stocks = resolve_auction_stocks(codes)
    if not stocks:
        return {"outcome": "error", "reason": "no_codes"}

    day = on_date or today_cn()
    if not force and not is_trading_day(day):
        save_watch_manifest(outcome="skip", on_date=day, message="非交易日")
        return {"outcome": "skip", "message": "非交易日"}

    schedule, interval = _schedule_times(day)
    if force:
        schedule = [datetime.now(_CN_TZ)]
    reset_auction_series(on_date=day)

    t0 = time.monotonic()
    collected = 0
    code_list = [s.code for s in stocks]

    try:
        for idx, scheduled in enumerate(schedule):
            if not force:
                _sleep_until(scheduled)
            is_final = idx == len(schedule) - 1
            snaps = build_auction_snapshots(stocks)
            captured_at = datetime.now(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
            append_auction_series_point(snaps, captured_at=captured_at, on_date=day, is_final=is_final)
            collected += 1
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        save_watch_manifest(
            outcome="error",
            on_date=day,
            point_count=collected,
            stock_count=len(stocks),
            duration_ms=duration_ms,
            message=str(exc),
        )
        return {"outcome": "error", "message": str(exc), "point_count": collected, "codes": code_list}

    series = load_auction_series(on_date=day)
    trend_path = write_auction_trend(on_date=day, series_points=series)
    duration_ms = int((time.monotonic() - t0) * 1000)
    save_watch_manifest(
        outcome="ok",
        on_date=day,
        point_count=len(series),
        stock_count=len(stocks),
        duration_ms=duration_ms,
    )
    return {
        "outcome": "ok",
        "codes": code_list,
        "stock_count": len(stocks),
        "point_count": len(series),
        "interval_sec": interval,
        "trend_path": str(trend_path),
        "duration_ms": duration_ms,
    }
