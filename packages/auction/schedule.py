"""集合竞价采样时刻表。"""
from __future__ import annotations

from datetime import date, datetime, time as dt_time
from zoneinfo import ZoneInfo

from core.config import auction_cfg
from core.trading_schedule import build_interval_schedule, parse_hms

_CN_TZ = ZoneInfo("Asia/Shanghai")


def auction_schedule_times(on_date: date) -> tuple[list[datetime], int]:
    cfg = auction_cfg()
    start_t = parse_hms(str(cfg.get("watch_start") or "09:15:05"), dt_time(9, 15, 5))
    end_t = parse_hms(str(cfg.get("watch_end") or "09:25:05"), dt_time(9, 25, 5))
    interval = max(1, int(cfg.get("interval_sec") or 30))
    return build_interval_schedule(
        on_date,
        start_t=start_t,
        end_t=end_t,
        interval_sec=interval,
        tz=_CN_TZ,
    )
