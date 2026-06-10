"""第 3 步 3.7C · 定稿落盘 midday_context（无 3.8 B 层 digest）。"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR

_CONTEXT_DIR = DATA_DIR / "midday_context"


def finalize_midday_context(
    skeleton: dict[str, Any],
    *,
    trade_date: date,
) -> dict[str, Any]:
    ctx = dict(skeleton)
    meta = dict(ctx.get("meta") or {})
    meta["pipeline_step"] = "3.7"
    meta["context_as_of"] = meta.get("context_as_of") or now_iso()
    ctx["meta"] = meta

    path = _CONTEXT_DIR / f"{trade_date.isoformat()}.json"
    atomic_write_text(path, json.dumps(ctx, ensure_ascii=False, indent=2))
    ctx["path"] = str(path)
    return ctx


__all__ = ["finalize_midday_context"]
