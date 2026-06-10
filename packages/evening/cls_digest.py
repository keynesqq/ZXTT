"""第 3 步 3.8 · 财联社 B 层 digest。"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

from ai.llm import chat, digest_timeout_sec, parse_json_blob
from ai.prompts import DIGEST_CLS_SYSTEM
from core.config import evening_cfg
from core.config import normalize_code as norm_code
from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR
from market.cls.daily_articles import ARTICLE_SLOTS

_DIGEST_DIR = DATA_DIR / "ai_digest"


def _local_cls_digest(content: str, title: str) -> dict[str, Any]:
    text = (content or "").strip()
    if len(text) > 400:
        text = text[:400] + "…"
    codes = re.findall(r"\b[036]\d{5}\b", content or "")
    return {
        "summary": text or title,
        "themes": [],
        "risks": [],
        "mentioned_codes": list(dict.fromkeys(codes))[:20],
        "facts": [],
        "ok": True,
        "model": "local",
        "digested_at": now_iso(),
    }


def _digest_article(slot_key: str, article: dict[str, Any]) -> dict[str, Any]:
    title = str(article.get("title") or slot_key)
    content = str(article.get("content") or "")
    threshold = int(evening_cfg().get("cls_short_local_threshold") or 200)
    if len(content) < threshold:
        out = _local_cls_digest(content, title)
        out["status"] = "local_short"
        return out
    user = f"栏目={slot_key}\n标题={title}\n\n{content}"
    raw, model, err = chat(
        DIGEST_CLS_SYSTEM,
        user,
        max_tokens=int(evening_cfg().get("cls_digest_max_tokens") or 2500),
        timeout_sec=digest_timeout_sec(),
    )
    if err or not raw:
        out = _local_cls_digest(content, title)
        out["digest_error"] = err or "empty_response"
        out["status"] = "local_fallback"
        return out
    parsed = parse_json_blob(raw)
    parsed["ok"] = True
    parsed["model"] = model
    parsed["digested_at"] = now_iso()
    parsed["status"] = "ok"
    parsed["title"] = title
    return parsed


def run_cls_digest(
    bundle: dict[str, Any],
    *,
    trade_date: date,
    whitelist_codes: set[str] | None = None,
) -> dict[str, Any]:
    cls_art = (bundle.get("market") or {}).get("cls_articles") or {}
    articles = cls_art.get("articles") or {}
    workers = min(int(evening_cfg().get("cls_digest_workers") or 3), 3)
    wl = whitelist_codes or set((bundle.get("by_code") or {}).keys())

    slots_out: dict[str, Any] = {}
    mentions: dict[str, list[str]] = {}

    def _one(slot: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        key = slot["key"]
        art = articles.get(key)
        if not art or not art.get("content"):
            return key, {"status": "missing", "ok": False, "label": slot.get("label", key)}
        digest = _digest_article(key, art)
        path = _DIGEST_DIR / trade_date.isoformat() / f"cls_{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(digest, ensure_ascii=False, indent=2))
        return key, {**digest, "path": str(path), "label": slot.get("label", key)}

    keys = [s for s in ARTICLE_SLOTS]
    if workers <= 1:
        results = [_one(s) for s in keys]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_one, keys))

    found = 0
    for key, rec in results:
        slots_out[key] = rec
        if rec.get("ok"):
            found += 1
        for raw_code in rec.get("mentioned_codes") or []:
            code = norm_code(str(raw_code))
            if code in wl:
                mentions.setdefault(code, []).append(key)

    expected = len(ARTICLE_SLOTS)
    prompt_cls_lines = []
    for slot in ARTICLE_SLOTS:
        key = slot["key"]
        rec = slots_out.get(key) or {}
        if rec.get("ok"):
            prompt_cls_lines.append(f"## {slot['label']}\n{rec.get('summary','')}")
        else:
            prompt_cls_lines.append(f"## {slot['label']}\n（缺篇或 digest 失败）")

    return {
        "cls_digest": {
            "complete": found >= expected,
            "found": found,
            "expected": expected,
            "slots": slots_out,
        },
        "cls_mentions_by_code": mentions,
        "prompt_cls": "\n\n".join(prompt_cls_lines),
        "digested_at": now_iso(),
    }


__all__ = ["run_cls_digest"]
