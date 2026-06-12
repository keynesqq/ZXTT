"""各采集段是否算「已完成」（供 --resume 判定）。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from core.paths import DATA_DIR

MIN_AUCTION_POINTS = 2


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def auction_phase_complete(on_date: date) -> bool:
    manifest = _load_json(DATA_DIR / "last_auction_watch.json")
    if not manifest or manifest.get("calendar_date") != on_date.isoformat():
        return False
    if manifest.get("outcome") != "ok":
        return False
    if int(manifest.get("point_count") or 0) < MIN_AUCTION_POINTS:
        return False
    return (DATA_DIR / f"auction_trend_{on_date.isoformat()}.json").is_file()


def segment_points_complete(points: list[dict], *, min_points: int = 2) -> bool:
    if len(points) < min_points:
        return False
    return bool(points[-1].get("is_final"))
