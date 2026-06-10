from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.paths import DATA_DIR
from core.trading_calendar import today_cn
from quote.auction_snap import AuctionSnap, snap_to_dict

_CN_TZ = ZoneInfo("Asia/Shanghai")
SCHEMA_VERSION = 1


def _series_path(on_date: date) -> Path:
    return DATA_DIR / f"auction_series_{on_date.isoformat()}.json"


def reset_auction_series(*, on_date: date) -> None:
    path = _series_path(on_date)
    if path.is_file():
        path.unlink()


def load_auction_series(*, on_date: date | None = None) -> list[dict]:
    day = on_date or today_cn()
    path = _series_path(day)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    points = data.get("points") if isinstance(data, dict) else None
    return points if isinstance(points, list) else []


def write_auction_series(points: list[dict], *, on_date: date) -> Path:
    path = _series_path(on_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = ""
    if points:
        ts = str(points[-1].get("captured_at") or "")
    if not ts:
        ts = datetime.now(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "calendar_date": on_date.isoformat(),
        "points": points,
        "updated_at": ts,
        "source": "simulate",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def append_auction_series_point(
    snaps: list[AuctionSnap],
    *,
    captured_at: str | None = None,
    on_date: date | None = None,
    is_final: bool = False,
) -> Path:
    day = on_date or today_cn()
    path = _series_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = captured_at or datetime.now(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    point = {
        "captured_at": ts,
        "is_final": is_final,
        "rows": [snap_to_dict(s, is_final=is_final) for s in snaps],
    }
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    else:
        data = {}
    points = data.get("points") if isinstance(data, dict) else None
    if not isinstance(points, list):
        points = []
    points.append(point)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "calendar_date": day.isoformat(),
        "points": points,
        "updated_at": ts,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

