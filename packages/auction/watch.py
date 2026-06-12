"""集合竞价走势：按用户提供的个股列表，9:15–9:25 每 30 秒采一次，最后汇总走势。"""
from __future__ import annotations

import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from auction.manifest import save_watch_manifest
from auction.schedule import auction_schedule_times as _schedule_times
from auction.series import append_auction_series_point, load_auction_series, reset_auction_series
from auction.stocks import resolve_auction_stocks
from auction.trajectory import write_auction_trend
from core.phase_complete import auction_phase_complete
from core.schedule_guard import require_collect_schedule, sleep_until
from core.trading_calendar import is_trading_day, today_cn
from quote.auction_snap import build_auction_snapshots

_CN_TZ = ZoneInfo("Asia/Shanghai")


def run_auction_watch(
    codes: list[str],
    *,
    force: bool = False,
    on_date: date | None = None,
    reset: bool = True,
    resume: bool = False,
    schedule: list[datetime] | None = None,
) -> dict:
    """采集集合竞价走势；codes 为必填个股列表（一只或多只）。"""
    stocks = resolve_auction_stocks(codes)
    if not stocks:
        return {"outcome": "error", "reason": "no_codes"}

    day = on_date or today_cn()
    if not force and not is_trading_day(day):
        save_watch_manifest(outcome="skip", on_date=day, message="非交易日")
        return {"outcome": "skip", "message": "非交易日"}

    code_list = [s.code for s in stocks]
    full_schedule, interval = _schedule_times(day)
    existing_points = load_auction_series(on_date=day) if resume else []
    auction_partial = bool(existing_points) and not auction_phase_complete(day)

    if force:
        schedule = [datetime.now(_CN_TZ)]
    elif schedule is None:
        schedule = require_collect_schedule(
            full_schedule,
            phase="auction",
            force=False,
            on_date=day,
            resume=resume,
            existing_points=existing_points,
            incomplete=auction_partial,
        )

    final_at = full_schedule[-1]

    if reset and not auction_partial:
        reset_auction_series(on_date=day)
        existing_points = []

    if not schedule:
        series = load_auction_series(on_date=day)
        if series:
            trend_path = write_auction_trend(on_date=day, series_points=series)
            return {
                "outcome": "ok",
                "codes": code_list,
                "stock_count": len(stocks),
                "point_count": len(series),
                "interval_sec": interval,
                "trend_path": str(trend_path),
                "duration_ms": 0,
            }

    t0 = time.monotonic()

    try:
        for scheduled in schedule:
            if not force:
                sleep_until(scheduled)
            is_final = scheduled == final_at
            snaps = build_auction_snapshots(stocks)
            captured_at = scheduled.strftime("%Y-%m-%d %H:%M:%S")
            append_auction_series_point(snaps, captured_at=captured_at, on_date=day, is_final=is_final)
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        total = len(load_auction_series(on_date=day))
        save_watch_manifest(
            outcome="error",
            on_date=day,
            point_count=total,
            stock_count=len(stocks),
            duration_ms=duration_ms,
            message=str(exc),
        )
        return {"outcome": "error", "message": str(exc), "point_count": total, "codes": code_list}

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
