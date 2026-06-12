"""用模拟数据跑通集合竞价完整链路（无网络、无同花顺）。"""
from __future__ import annotations

import time
from datetime import date

from auction.manifest import save_watch_manifest
from auction.mock import DEMO_DATE_ISO, build_mock_series_points, mock_stocks
from auction.series import write_auction_series
from auction.trajectory import build_auction_trends, write_auction_trend
from auction.schedule import auction_schedule_times as _schedule_times


def _demo_date(on_date: date | None) -> date:
    return on_date or date.fromisoformat(DEMO_DATE_ISO)


def run_auction_simulate(*, on_date: date | None = None) -> dict:
    day = _demo_date(on_date)
    schedule, interval = _schedule_times(day)
    stocks = mock_stocks()
    t0 = time.monotonic()

    points = build_mock_series_points(schedule, stocks=stocks)
    write_auction_series(points, on_date=day)

    trends = build_auction_trends(points)
    trend_path = write_auction_trend(on_date=day, series_points=points)
    shapes = {t["code"]: t["shape"] for t in trends}
    expected = {s.code: s.expected_shape for s in stocks}
    mismatches = {c: {"expected": expected[c], "got": shapes.get(c)} for c in expected if shapes.get(c) != expected[c]}

    duration_ms = int((time.monotonic() - t0) * 1000)
    save_watch_manifest(
        outcome="ok",
        on_date=day,
        point_count=len(points),
        stock_count=len(stocks),
        duration_ms=duration_ms,
        message="simulate",
    )
    return {
        "outcome": "ok",
        "mode": "simulate",
        "calendar_date": day.isoformat(),
        "point_count": len(points),
        "stock_count": len(stocks),
        "interval_sec": interval,
        "schedule_start": schedule[0].strftime("%H:%M:%S") if schedule else "",
        "schedule_end": schedule[-1].strftime("%H:%M:%S") if schedule else "",
        "trend_path": str(trend_path),
        "shapes": shapes,
        "shape_mismatches": mismatches,
        "duration_ms": duration_ms,
    }
