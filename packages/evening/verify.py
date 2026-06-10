"""第 4 步 4D · 可选事实校验（MVP 占位）。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR


def run_evening_verify(day: date, *, ai_text: str, ctx: dict[str, Any]) -> dict[str, Any]:
    """MVP：记录校验占位，不阻断落盘。"""
    path = DATA_DIR / "ai_digest" / day.isoformat() / "verify.json"
    payload = {
        "schema_version": 1,
        "trade_date": day.isoformat(),
        "overall": "skip",
        "message": "verify_mvp_placeholder",
        "at": now_iso(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


__all__ = ["run_evening_verify"]
