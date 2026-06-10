"""等待竞价采集完成。"""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from core.config import morning_cfg
from core.paths import DATA_DIR

_MANIFEST = DATA_DIR / "last_auction_watch.json"


def wait_auction_ready(
    day: date,
    *,
    max_sec: float | None = None,
) -> tuple[bool, dict]:
    limit = float(max_sec or morning_cfg().get("wait_auction_max_sec") or 15)
    t0 = time.monotonic()
    last: dict = {}
    while time.monotonic() - t0 < limit:
        if _MANIFEST.is_file():
            try:
                last = json.loads(_MANIFEST.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                last = {}
            if (
                str(last.get("calendar_date") or "") == day.isoformat()
                and last.get("outcome") == "ok"
                and int(last.get("point_count") or 0) >= 2
            ):
                return True, last
        time.sleep(0.5)
    return False, last


__all__ = ["wait_auction_ready"]
