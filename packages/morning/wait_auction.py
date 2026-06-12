"""等待竞价采集完成。"""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from auction.series import load_auction_series
from auction.trajectory import write_auction_trend
from core.config import morning_cfg
from core.paths import DATA_DIR

_MANIFEST = DATA_DIR / "last_auction_watch.json"


def _load_manifest() -> dict:
    if not _MANIFEST.is_file():
        return {}
    try:
        data = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _manifest_ready(day: date, manifest: dict) -> bool:
    return (
        str(manifest.get("calendar_date") or "") == day.isoformat()
        and manifest.get("outcome") == "ok"
        and int(manifest.get("point_count") or 0) >= 2
    )


def _try_rebuild_trend(day: date) -> bool:
    points = load_auction_series(on_date=day)
    if len(points) < 2 or not points[-1].get("is_final"):
        return False
    write_auction_trend(on_date=day, series_points=points)
    return (DATA_DIR / f"auction_trend_{day.isoformat()}.json").is_file()


def wait_auction_ready(
    day: date,
    *,
    max_sec: float | None = None,
) -> tuple[bool, dict]:
    limit = float(max_sec or morning_cfg().get("wait_auction_max_sec") or 15)
    t0 = time.monotonic()
    last: dict = {}
    while time.monotonic() - t0 < limit:
        last = _load_manifest()
        if _manifest_ready(day, last):
            return True, last
        if _try_rebuild_trend(day):
            return True, last or _load_manifest()
        time.sleep(0.5)
    if _try_rebuild_trend(day):
        return True, last or _load_manifest()
    return False, last


__all__ = ["wait_auction_ready"]
