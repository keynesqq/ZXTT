"""用模拟数据跑通上午+下午分段采集与合并（无网络）。"""
from __future__ import annotations

import time
from datetime import date

from intraday.manifest import save_watch_manifest
from intraday.mock import DEMO_DATE_ISO, build_mock_series_points, mock_stocks
from intraday.series import write_intraday_segment, write_merged_intraday_series
from intraday.watch import _schedule_afternoon, _schedule_morning


def _demo_date(on_date: date | None) -> date:
    return on_date or date.fromisoformat(DEMO_DATE_ISO)


def run_intraday_simulate(*, on_date: date | None = None) -> dict:
    day = _demo_date(on_date)
    morning_schedule, interval = _schedule_morning(day)
    afternoon_schedule, _ = _schedule_afternoon(day)
    stocks = mock_stocks()
    t0 = time.monotonic()

    morning_points = build_mock_series_points(morning_schedule, stocks=stocks, segment="morning")
    afternoon_points = build_mock_series_points(afternoon_schedule, stocks=stocks, segment="afternoon")
    write_intraday_segment(morning_points, on_date=day, segment="morning", source="simulate")
    write_intraday_segment(afternoon_points, on_date=day, segment="afternoon", source="simulate")
    merged_path = write_merged_intraday_series(on_date=day)

    duration_ms = int((time.monotonic() - t0) * 1000)
    save_watch_manifest(
        outcome="ok",
        on_date=day,
        morning_point_count=len(morning_points),
        afternoon_point_count=len(afternoon_points),
        merged_point_count=len(morning_points) + len(afternoon_points),
        stock_count=len(stocks),
        duration_ms=duration_ms,
        message="simulate",
    )
    day_iso = day.isoformat()
    return {
        "outcome": "ok",
        "mode": "simulate",
        "calendar_date": day_iso,
        "morning_point_count": len(morning_points),
        "afternoon_point_count": len(afternoon_points),
        "merged_point_count": len(morning_points) + len(afternoon_points),
        "stock_count": len(stocks),
        "interval_sec": interval,
        "morning_start": morning_schedule[0].strftime("%H:%M:%S") if morning_schedule else "",
        "morning_end": morning_schedule[-1].strftime("%H:%M:%S") if morning_schedule else "",
        "afternoon_start": afternoon_schedule[0].strftime("%H:%M:%S") if afternoon_schedule else "",
        "afternoon_end": afternoon_schedule[-1].strftime("%H:%M:%S") if afternoon_schedule else "",
        "morning_path": f"data/intraday_series_{day_iso}_morning.json",
        "afternoon_path": f"data/intraday_series_{day_iso}_afternoon.json",
        "series_path": f"data/intraday_series_{day_iso}.json",
        "merged_path": str(merged_path),
        "duration_ms": duration_ms,
    }
