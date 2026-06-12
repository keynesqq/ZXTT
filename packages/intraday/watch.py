"""盘中分钟序列：上午 9:30–11:30、下午 13:00–15:00，分段保存后合并。"""
from __future__ import annotations

import time
from datetime import date, datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo

from core.config import intraday_cfg
from core.trading_calendar import is_trading_day, today_cn
from intraday.manifest import save_watch_manifest
from intraday.series import (
    append_intraday_segment_point,
    load_intraday_segment,
    reset_intraday_series,
    reset_intraday_segment,
    write_merged_intraday_series,
)
from intraday.stocks import resolve_intraday_stocks
from quote.snapshot.build import build_snapshots, snapshot_row_dict
from watchlist.ths_blocks import StockItem

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


def _interval_sec() -> int:
    return max(1, int(intraday_cfg().get("interval_sec") or 60))


def _window_times(start_key: str, end_key: str, *, default_start: dt_time, default_end: dt_time) -> tuple[dt_time, dt_time]:
    cfg = intraday_cfg()
    start_t = _parse_hms(str(cfg.get(start_key) or ""), default_start)
    end_t = _parse_hms(str(cfg.get(end_key) or ""), default_end)
    return start_t, end_t


def _schedule_window(on_date: date, *, start_t: dt_time, end_t: dt_time) -> tuple[list[datetime], int]:
    interval = _interval_sec()
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


def _schedule_morning(on_date: date) -> tuple[list[datetime], int]:
    cfg = intraday_cfg()
    start_t, end_t = _window_times(
        "morning_start",
        "morning_end",
        default_start=_parse_hms(str(cfg.get("watch_start") or "09:30:00"), dt_time(9, 30, 0)),
        default_end=_parse_hms(str(cfg.get("watch_end") or "11:30:00"), dt_time(11, 30, 0)),
    )
    return _schedule_window(on_date, start_t=start_t, end_t=end_t)


def _schedule_afternoon(on_date: date) -> tuple[list[datetime], int]:
    start_t, end_t = _window_times(
        "afternoon_start",
        "afternoon_end",
        default_start=dt_time(13, 0, 0),
        default_end=dt_time(15, 0, 0),
    )
    return _schedule_window(on_date, start_t=start_t, end_t=end_t)


def _schedule_times(on_date: date) -> tuple[list[datetime], int]:
    return _schedule_morning(on_date)


def _sleep_until(target: datetime) -> None:
    now = datetime.now(_CN_TZ)
    sec = (target - now).total_seconds()
    if sec > 0:
        time.sleep(sec)


def _collect_segment(
    stocks: list[StockItem],
    schedule: list[datetime],
    day: date,
    *,
    segment: str,
    force: bool,
) -> int:
    reset_intraday_segment(on_date=day, segment=segment)
    for idx, scheduled in enumerate(schedule):
        if not force:
            _sleep_until(scheduled)
        is_final = idx == len(schedule) - 1
        rows = build_snapshots(stocks, fetch_industry=False, record_manifest=False)
        quotes = [snapshot_row_dict(r) for r in rows]
        captured_at = datetime.now(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
        append_intraday_segment_point(
            quotes,
            captured_at=captured_at,
            on_date=day,
            segment=segment,
            is_final=is_final,
        )
    return len(schedule)


def run_intraday_watch(
    codes: list[str],
    *,
    force: bool = False,
    on_date: date | None = None,
    session: str = "all",
) -> dict:
    """采集盘中分钟序列。session=all 时上午结束后保存，等到 13:00 采下午，再合并。"""
    if session not in ("all", "morning", "afternoon"):
        return {"outcome": "error", "reason": "invalid_session", "session": session}

    stocks = resolve_intraday_stocks(codes, on_date=on_date)
    if not stocks:
        return {"outcome": "error", "reason": "no_codes"}

    day = on_date or today_cn()
    if not force and not is_trading_day(day):
        save_watch_manifest(outcome="skip", on_date=day, message="非交易日", session=session)
        return {"outcome": "skip", "message": "非交易日"}

    morning_schedule, interval = _schedule_morning(day)
    afternoon_schedule, _ = _schedule_afternoon(day)
    if force:
        morning_schedule = [datetime.now(_CN_TZ)]
        afternoon_schedule = [datetime.now(_CN_TZ)]

    if session == "all":
        reset_intraday_series(on_date=day)
    elif session == "morning":
        reset_intraday_segment(on_date=day, segment="morning")
    elif session == "afternoon":
        reset_intraday_segment(on_date=day, segment="afternoon")

    t0 = time.monotonic()
    code_list = [s.code for s in stocks]
    morning_count = 0
    afternoon_count = 0

    try:
        if session in ("all", "morning"):
            morning_count = _collect_segment(
                stocks,
                morning_schedule,
                day,
                segment="morning",
                force=force,
            )

        if session in ("all", "afternoon"):
            if session == "all" and not force:
                _, afternoon_start_t = _window_times(
                    "afternoon_start",
                    "afternoon_end",
                    default_start=dt_time(13, 0, 0),
                    default_end=dt_time(15, 0, 0),
                )
                _sleep_until(datetime.combine(day, afternoon_start_t, tzinfo=_CN_TZ))
            afternoon_count = _collect_segment(
                stocks,
                afternoon_schedule,
                day,
                segment="afternoon",
                force=force,
            )

        merged_path = None
        if session in ("all", "afternoon"):
            merged_path = write_merged_intraday_series(on_date=day)
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        save_watch_manifest(
            outcome="error",
            on_date=day,
            morning_point_count=morning_count,
            afternoon_point_count=afternoon_count,
            stock_count=len(stocks),
            duration_ms=duration_ms,
            message=str(exc),
            session=session,
        )
        return {
            "outcome": "error",
            "message": str(exc),
            "morning_point_count": morning_count,
            "afternoon_point_count": afternoon_count,
            "codes": code_list,
            "session": session,
        }

    morning_saved = len(load_intraday_segment(on_date=day, segment="morning"))
    afternoon_saved = len(load_intraday_segment(on_date=day, segment="afternoon"))
    merged_count = morning_saved + afternoon_saved if session in ("all", "afternoon") else morning_saved

    duration_ms = int((time.monotonic() - t0) * 1000)
    save_watch_manifest(
        outcome="ok",
        on_date=day,
        morning_point_count=morning_saved,
        afternoon_point_count=afternoon_saved,
        merged_point_count=merged_count,
        stock_count=len(stocks),
        duration_ms=duration_ms,
        session=session,
    )

    day_iso = day.isoformat()
    result: dict = {
        "outcome": "ok",
        "session": session,
        "codes": code_list,
        "stock_count": len(stocks),
        "interval_sec": interval,
        "morning_point_count": morning_saved,
        "morning_path": f"data/intraday_series_{day_iso}_morning.json",
        "duration_ms": duration_ms,
    }
    if session in ("all", "afternoon"):
        result["afternoon_point_count"] = afternoon_saved
        result["afternoon_path"] = f"data/intraday_series_{day_iso}_afternoon.json"
        result["merged_point_count"] = merged_count
        result["series_path"] = f"data/intraday_series_{day_iso}.json"
        if merged_path is not None:
            result["merged_path"] = str(merged_path)
    return result
