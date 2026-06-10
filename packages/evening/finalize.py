"""第 3 步 3.8C · 定稿落盘 evening_context。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from core.context_as_of import max_ts_iso, now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR

_CONTEXT_DIR = DATA_DIR / "evening_context"


def finalize_evening_context(
    skeleton: dict[str, Any],
    cls_result: dict[str, Any],
    *,
    trade_date: date,
) -> dict[str, Any]:
    ctx = dict(skeleton)
    ctx["cls_digest"] = cls_result.get("cls_digest") or {}
    ctx["cls_mentions_by_code"] = cls_result.get("cls_mentions_by_code") or {}
    prompt = dict(ctx.get("prompt") or {})
    prompt["cls"] = cls_result.get("prompt_cls") or ""
    ctx["prompt"] = prompt

    meta = dict(ctx.get("meta") or {})
    meta["pipeline_step"] = "3.7+3.8"
    cls_found = (ctx["cls_digest"].get("found") or 0)
    cls_exp = (ctx["cls_digest"].get("expected") or 5)
    meta["cls_articles_found"] = f"{cls_found}/{cls_exp}"
    meta["context_as_of"] = max_ts_iso(
        str(meta.get("context_as_of") or ""),
        cls_result.get("digested_at"),
        now_iso(),
    )
    ctx["meta"] = meta

    path = _CONTEXT_DIR / f"{trade_date.isoformat()}.json"
    atomic_write_text(path, json.dumps(ctx, ensure_ascii=False, indent=2))
    ctx["path"] = str(path)
    return ctx


__all__ = ["finalize_evening_context"]
