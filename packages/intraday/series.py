from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.paths import DATA_DIR
from core.trading_calendar import today_cn

_CN_TZ = ZoneInfo("Asia/Shanghai")
SCHEMA_VERSION = 1
MERGED_SCHEMA_VERSION = 2
SEGMENTS = ("morning", "afternoon")


def _segment_path(on_date: date, segment: str) -> Path:
    return DATA_DIR / f"intraday_series_{on_date.isoformat()}_{segment}.json"


def _merged_path(on_date: date) -> Path:
    return DATA_DIR / f"intraday_series_{on_date.isoformat()}.json"


def reset_intraday_segment(*, on_date: date, segment: str) -> None:
    path = _segment_path(on_date, segment)
    if path.is_file():
        path.unlink()


def reset_intraday_series(*, on_date: date) -> None:
    for segment in SEGMENTS:
        reset_intraday_segment(on_date=on_date, segment=segment)
    clear_merged_intraday_series(on_date=on_date)


def clear_merged_intraday_series(*, on_date: date) -> None:
    path = _merged_path(on_date)
    if path.is_file():
        path.unlink()


def load_intraday_segment(*, on_date: date | None = None, segment: str) -> list[dict]:
    day = on_date or today_cn()
    path = _segment_path(day, segment)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    points = data.get("points") if isinstance(data, dict) else None
    return points if isinstance(points, list) else []


def load_intraday_series(*, on_date: date | None = None) -> list[dict]:
    day = on_date or today_cn()
    merged = _merged_path(day)
    if merged.is_file():
        try:
            data = json.loads(merged.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        points = data.get("points") if isinstance(data, dict) else None
        return points if isinstance(points, list) else []
    morning = load_intraday_segment(on_date=day, segment="morning")
    afternoon = load_intraday_segment(on_date=day, segment="afternoon")
    if morning or afternoon:
        return _merge_points(morning, afternoon)
    return []


def _merge_points(morning: list[dict], afternoon: list[dict]) -> list[dict]:
    combined = list(morning) + list(afternoon)
    combined.sort(key=lambda p: str(p.get("captured_at") or ""))
    return combined


def write_intraday_segment(
    points: list[dict],
    *,
    on_date: date,
    segment: str,
    source: str = "",
) -> Path:
    path = _segment_path(on_date, segment)
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = ""
    if points:
        ts = str(points[-1].get("captured_at") or "")
    if not ts:
        ts = datetime.now(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    payload: dict = {
        "schema_version": SCHEMA_VERSION,
        "calendar_date": on_date.isoformat(),
        "segment": segment,
        "points": points,
        "updated_at": ts,
    }
    if source:
        payload["source"] = source
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_merged_intraday_series(*, on_date: date) -> Path:
    morning = load_intraday_segment(on_date=on_date, segment="morning")
    afternoon = load_intraday_segment(on_date=on_date, segment="afternoon")
    points = _merge_points(morning, afternoon)
    path = _merged_path(on_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = str(points[-1].get("captured_at") or "") if points else datetime.now(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "schema_version": MERGED_SCHEMA_VERSION,
        "calendar_date": on_date.isoformat(),
        "sessions": {
            "morning": {
                "point_count": len(morning),
                "path": f"data/intraday_series_{on_date.isoformat()}_morning.json",
            },
            "afternoon": {
                "point_count": len(afternoon),
                "path": f"data/intraday_series_{on_date.isoformat()}_afternoon.json",
            },
        },
        "point_count": len(points),
        "points": points,
        "updated_at": ts,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_intraday_series(points: list[dict], *, on_date: date) -> Path:
    """兼容 simulate：整段写入 morning 并合并。"""
    write_intraday_segment(points, on_date=on_date, segment="morning", source="simulate")
    return write_merged_intraday_series(on_date=on_date)


def append_intraday_segment_point(
    rows: list[dict],
    *,
    captured_at: str | None = None,
    on_date: date | None = None,
    segment: str,
    is_final: bool = False,
) -> Path:
    day = on_date or today_cn()
    path = _segment_path(day, segment)
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = captured_at or datetime.now(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    point = {
        "captured_at": ts,
        "is_final": is_final,
        "segment": segment,
        "rows": rows,
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
        "segment": segment,
        "points": points,
        "updated_at": ts,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def append_intraday_series_point(
    rows: list[dict],
    *,
    captured_at: str | None = None,
    on_date: date | None = None,
    is_final: bool = False,
) -> Path:
    return append_intraday_segment_point(
        rows,
        captured_at=captured_at,
        on_date=on_date,
        segment="morning",
        is_final=is_final,
    )
