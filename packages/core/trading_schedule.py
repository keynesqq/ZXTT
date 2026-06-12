"""交易时段内按固定间隔生成采样时刻表。"""
from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo

_CN_TZ = ZoneInfo("Asia/Shanghai")


def parse_hms(raw: str, default: dt_time) -> dt_time:
    parts = str(raw or "").strip().split(":")
    if len(parts) < 2:
        return default
    try:
        h, m = int(parts[0]), int(parts[1])
        s = int(parts[2]) if len(parts) >= 3 else 0
        return dt_time(h, m, s)
    except ValueError:
        return default


def build_interval_schedule(
    on_date: date,
    *,
    start_t: dt_time,
    end_t: dt_time,
    interval_sec: int,
    tz: ZoneInfo = _CN_TZ,
) -> tuple[list[datetime], int]:
    interval = max(1, int(interval_sec))
    start = datetime.combine(on_date, start_t, tzinfo=tz)
    end = datetime.combine(on_date, end_t, tzinfo=tz)
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
