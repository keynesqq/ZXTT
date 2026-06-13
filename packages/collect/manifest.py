"""统一采集 manifest（P1）：记录各信息源采集结果与耗时。"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from core.context_as_of import now_iso
from core.paths import ROOT

_MANIFEST_DIR = "data/collect_manifest"


def _manifest_path(trade_date: date) -> Path:
    return ROOT / _MANIFEST_DIR / f"{trade_date.isoformat()}.json"


def load_manifest(trade_date: date) -> dict[str, Any] | None:
    path = _manifest_path(trade_date)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _default_manifest(*, trade_date: date, calendar_date: date | None = None) -> dict[str, Any]:
    cal = calendar_date or trade_date
    return {
        "trade_date": trade_date.isoformat(),
        "calendar_date": cal.isoformat(),
        "sources": {},
    }


def record_source(
    trade_date: date,
    name: str,
    record: dict[str, Any],
    *,
    calendar_date: date | None = None,
) -> None:
    """合并写入单源采集记录。"""
    path = _manifest_path(trade_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = load_manifest(trade_date) or _default_manifest(
        trade_date=trade_date, calendar_date=calendar_date
    )
    if calendar_date:
        payload["calendar_date"] = calendar_date.isoformat()
    merged = dict(payload.get("sources", {}).get(name) or {})
    merged.update(record)
    merged.setdefault("at_iso", now_iso())
    merged["updated_at_iso"] = now_iso()
    payload.setdefault("sources", {})[name] = merged
    payload["updated_at_iso"] = now_iso()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        from core.trading_calendar import market_data_date
        from report.hub import refresh_hub_feed

        refresh_hub_feed(market_data_date(trade_date))
    except Exception:
        pass


@contextmanager
def track_source(
    trade_date: date,
    name: str,
    *,
    calendar_date: date | None = None,
) -> Iterator[dict[str, Any]]:
    """计时并在退出时写入 manifest（异常时 ok=false）。"""
    rec: dict[str, Any] = {"ok": True}
    started_at_iso = now_iso()
    t0 = time.monotonic()
    err: Exception | None = None
    try:
        yield rec
    except Exception as e:
        err = e
        rec["ok"] = False
        rec["error"] = str(e)
        raise
    finally:
        rec["started_at_iso"] = started_at_iso
        rec["finished_at_iso"] = now_iso()
        rec["duration_ms"] = int((time.monotonic() - t0) * 1000)
        if err is None and "ok" not in rec:
            rec["ok"] = True
        record_source(trade_date, name, rec, calendar_date=calendar_date)
