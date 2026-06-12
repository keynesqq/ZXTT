"""全天监控：竞价（独立文件）+ 正式交易分段采集与合并。"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, time as dt_time
from zoneinfo import ZoneInfo

from auction.watch import run_auction_watch
from core.config import intraday_cfg
from core.paths import DATA_DIR
from core.trading_calendar import is_trading_day, today_cn
from intraday.manifest import save_watch_manifest
from intraday.resume import auction_phase_complete, phase_status, resolve_phases
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
VALID_SESSIONS = frozenset({"all", "auction", "morning", "afternoon"})


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
    from datetime import timedelta

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


def _schedule_auction(on_date: date) -> tuple[list[datetime], int]:
    from auction.watch import _schedule_times as auction_schedule

    return auction_schedule(on_date)


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


def _run_auction_phase(code_list: list[str], day: date, *, force: bool, reset: bool) -> dict:
    return run_auction_watch(code_list, force=force, on_date=day, reset=reset)


def run_intraday_watch(
    codes: list[str],
    *,
    force: bool = False,
    on_date: date | None = None,
    session: str = "all",
    resume: bool = False,
) -> dict:
    """全天监控。竞价写 auction_*（供早盘报告）；正式交易写 intraday_* 分段并合并。"""
    if session not in VALID_SESSIONS:
        return {"outcome": "error", "reason": "invalid_session", "session": session}

    stocks = resolve_intraday_stocks(codes, on_date=on_date)
    if not stocks:
        return {"outcome": "error", "reason": "no_codes"}

    day = on_date or today_cn()
    if not force and not is_trading_day(day):
        save_watch_manifest(outcome="skip", on_date=day, message="非交易日", session=session)
        return {"outcome": "skip", "message": "非交易日"}

    phases = resolve_phases(session=session, resume=resume, on_date=day)
    if not phases:
        status = phase_status(day)
        save_watch_manifest(
            outcome="ok",
            on_date=day,
            message="resume: all phases complete",
            session=session,
            phases_done=[p for p, done in status.items() if done],
        )
        return {"outcome": "ok", "session": session, "resume": True, "message": "各段已完成，无需续跑", "phases_done": status}

    morning_schedule, interval = _schedule_morning(day)
    afternoon_schedule, _ = _schedule_afternoon(day)
    auction_schedule, auction_interval = _schedule_auction(day)
    if force:
        auction_schedule = [datetime.now(_CN_TZ)]
        morning_schedule = [datetime.now(_CN_TZ)]
        afternoon_schedule = [datetime.now(_CN_TZ)]

    if session == "all" and not resume:
        reset_intraday_series(on_date=day)
    elif session == "morning":
        reset_intraday_segment(on_date=day, segment="morning")
    elif session == "afternoon":
        reset_intraday_segment(on_date=day, segment="afternoon")

    t0 = time.monotonic()
    code_list = [s.code for s in stocks]
    auction_count = 0
    morning_count = 0
    afternoon_count = 0
    auction_result: dict | None = None
    trend_path: str | None = None
    phases_done: list[str] = []
    day_iso = day.isoformat()

    try:
        if "auction" in phases:
            if session == "all" and not force:
                _sleep_until(auction_schedule[0])
            auction_result = _run_auction_phase(code_list, day, force=force, reset=True)
            if auction_result.get("outcome") != "ok":
                raise RuntimeError(str(auction_result.get("message") or "auction failed"))
            auction_count = int(auction_result.get("point_count") or 0)
            trend_path = str(auction_result.get("trend_path") or f"data/auction_trend_{day_iso}.json")
            phases_done.append("auction")

        if "morning" in phases:
            if session == "all" and not force and "auction" in phases:
                morning_start_t, _ = _window_times(
                    "morning_start",
                    "morning_end",
                    default_start=dt_time(9, 30, 0),
                    default_end=dt_time(11, 30, 0),
                )
                _sleep_until(datetime.combine(day, morning_start_t, tzinfo=_CN_TZ))
            elif session == "all" and not force and "auction" not in phases:
                morning_start_t, _ = _window_times(
                    "morning_start",
                    "morning_end",
                    default_start=dt_time(9, 30, 0),
                    default_end=dt_time(11, 30, 0),
                )
                _sleep_until(datetime.combine(day, morning_start_t, tzinfo=_CN_TZ))
            morning_count = _collect_segment(
                stocks,
                morning_schedule,
                day,
                segment="morning",
                force=force,
            )
            phases_done.append("morning")

        if "afternoon" in phases:
            if session == "all" and not force:
                afternoon_start_t, _ = _window_times(
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
            phases_done.append("afternoon")

        merged_path = None
        if "afternoon" in phases:
            merged_path = write_merged_intraday_series(on_date=day)
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        save_watch_manifest(
            outcome="error",
            on_date=day,
            auction_point_count=auction_count,
            morning_point_count=morning_count,
            afternoon_point_count=afternoon_count,
            stock_count=len(stocks),
            duration_ms=duration_ms,
            message=str(exc),
            session=session,
            phases_done=phases_done,
            last_phase=phases_done[-1] if phases_done else "",
        )
        return {
            "outcome": "error",
            "message": str(exc),
            "auction_point_count": auction_count,
            "morning_point_count": morning_count,
            "afternoon_point_count": afternoon_count,
            "codes": code_list,
            "session": session,
            "phases_done": phases_done,
        }

    morning_saved = len(load_intraday_segment(on_date=day, segment="morning"))
    afternoon_saved = len(load_intraday_segment(on_date=day, segment="afternoon"))
    if auction_count == 0 and auction_phase_complete(day):
        try:
            data = json.loads((DATA_DIR / "last_auction_watch.json").read_text(encoding="utf-8"))
            if data.get("calendar_date") == day_iso:
                auction_count = int(data.get("point_count") or 0)
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        if not trend_path:
            trend_path = f"data/auction_trend_{day_iso}.json"

    merged_count = morning_saved + afternoon_saved

    duration_ms = int((time.monotonic() - t0) * 1000)
    save_watch_manifest(
        outcome="ok",
        on_date=day,
        auction_point_count=auction_count,
        morning_point_count=morning_saved,
        afternoon_point_count=afternoon_saved,
        merged_point_count=merged_count,
        stock_count=len(stocks),
        duration_ms=duration_ms,
        session=session,
        phases_done=phases_done,
        last_phase=phases_done[-1] if phases_done else "",
    )

    result: dict = {
        "outcome": "ok",
        "session": session,
        "resume": resume,
        "codes": code_list,
        "stock_count": len(stocks),
        "interval_sec": interval,
        "auction_interval_sec": auction_interval,
        "phases_done": phases_done,
        "duration_ms": duration_ms,
    }
    if auction_count or "auction" in phases_done:
        result["auction_point_count"] = auction_count
        result["auction_series_path"] = f"data/auction_series_{day_iso}.json"
        result["auction_trend_path"] = trend_path or f"data/auction_trend_{day_iso}.json"
    if morning_saved or "morning" in phases_done:
        result["morning_point_count"] = morning_saved
        result["morning_path"] = f"data/intraday_series_{day_iso}_morning.json"
    if afternoon_saved or "afternoon" in phases_done:
        result["afternoon_point_count"] = afternoon_saved
        result["afternoon_path"] = f"data/intraday_series_{day_iso}_afternoon.json"
        result["merged_point_count"] = merged_count
        result["series_path"] = f"data/intraday_series_{day_iso}.json"
        if merged_path is not None:
            result["merged_path"] = str(merged_path)
    return result
