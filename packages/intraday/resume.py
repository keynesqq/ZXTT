"""分段完成检测与 --resume 续跑。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from core.paths import DATA_DIR
from intraday.series import load_intraday_segment

PHASES = ("auction", "morning", "afternoon")


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
    if int(manifest.get("point_count") or 0) < 2:
        return False
    return (DATA_DIR / f"auction_trend_{on_date.isoformat()}.json").is_file()


def intraday_segment_complete(on_date: date, segment: str) -> bool:
    points = load_intraday_segment(on_date=on_date, segment=segment)
    if not points:
        return False
    return bool(points[-1].get("is_final"))


def phase_status(on_date: date) -> dict[str, bool]:
    return {
        "auction": auction_phase_complete(on_date),
        "morning": intraday_segment_complete(on_date, "morning"),
        "afternoon": intraday_segment_complete(on_date, "afternoon"),
    }


def resolve_phases(*, session: str, resume: bool, on_date: date) -> list[str]:
    if session != "all":
        return [session]
    if not resume:
        return list(PHASES)
    status = phase_status(on_date)
    return [p for p in PHASES if not status.get(p)]
