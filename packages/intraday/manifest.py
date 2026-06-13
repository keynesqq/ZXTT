from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from core.paths import DATA_DIR
from core.trading_calendar import today_cn


def _manifest_path() -> Path:
    return DATA_DIR / "last_intraday_watch.json"


def save_watch_manifest(
    *,
    outcome: str,
    on_date: date | None = None,
    auction_point_count: int = 0,
    morning_point_count: int = 0,
    afternoon_point_count: int = 0,
    merged_point_count: int = 0,
    point_count: int = 0,
    stock_count: int = 0,
    duration_ms: int = 0,
    message: str = "",
    session: str = "all",
    phases_done: list[str] | None = None,
    last_phase: str = "",
) -> Path:
    day = on_date or today_cn()
    merged = merged_point_count or point_count or (morning_point_count + afternoon_point_count)
    payload = {
        "module": "intraday",
        "calendar_date": day.isoformat(),
        "session": session,
        "outcome": outcome,
        "auction_point_count": auction_point_count,
        "morning_point_count": morning_point_count,
        "afternoon_point_count": afternoon_point_count,
        "merged_point_count": merged,
        "point_count": merged,
        "stock_count": stock_count,
        "phases_done": phases_done or [],
        "last_phase": last_phase,
        "duration_ms": duration_ms,
        "finished_at": time.time(),
        "message": message,
    }
    path = _manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        from core.trading_calendar import market_data_date
        from report.hub import refresh_hub_feed

        refresh_hub_feed(market_data_date(day))
    except Exception:
        pass
    return path
