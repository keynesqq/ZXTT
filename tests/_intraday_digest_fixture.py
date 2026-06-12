"""测试用 intraday digest 最小 fixture。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from core.io import atomic_write_text
from core.paths import DATA_DIR


def minimal_intraday_digest_payload(day: date, *, segment: str = "morning") -> dict:
    stock = {
        "code": "600519",
        "name": "茅台",
        "session_shape": "震荡",
        "session_pct_chg": 1.0,
        "session_high_pct": 1.5,
        "session_low_pct": 0.2,
        "vs_auction_end_gap": 0.3,
        "limit_status": "正常",
        "shape_detail": "",
        "minute_point_count": 2,
    }
    if segment == "full":
        stock["morning_shape"] = "震荡"
        stock["afternoon_shape"] = "一路抬升"
        stock["vs_auction_end_gap_close"] = 0.8
    return {
        "schema_version": 1,
        "calendar_date": day.isoformat(),
        "segment": segment,
        "source": "test_fixture",
        "point_count": 121 if segment == "morning" else 242,
        "is_complete": True,
        "stock_count": 1,
        "stocks": [stock],
        "stocks_by_code": {stock["code"]: stock},
    }


def write_minimal_intraday_digest(day: date, *, segment: str = "morning") -> Path:
    payload = minimal_intraday_digest_payload(day, segment=segment)
    path = DATA_DIR / f"intraday_digest_{day.isoformat()}_{segment}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path
