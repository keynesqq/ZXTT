from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from core.paths import DATA_DIR
from core.trading_calendar import today_cn


def _manifest_path() -> Path:
    return DATA_DIR / "last_auction_watch.json"


def save_watch_manifest(
    *,
    outcome: str,
    on_date: date | None = None,
    point_count: int = 0,
    stock_count: int = 0,
    duration_ms: int = 0,
    message: str = "",
) -> Path:
    day = on_date or today_cn()
    payload = {
        "module": "auction",
        "calendar_date": day.isoformat(),
        "outcome": outcome,
        "point_count": point_count,
        "stock_count": stock_count,
        "duration_ms": duration_ms,
        "finished_at": time.time(),
        "message": message,
    }
    path = _manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
