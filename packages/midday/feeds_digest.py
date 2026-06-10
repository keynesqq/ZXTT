"""第 3 步 3.6 · feeds 指纹 + digest。"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any

from ai.llm import chat, digest_timeout_sec, parse_json_blob
from ai.prompts import DIGEST_STOCK_FEEDS_SYSTEM
from core.config import midday_cfg, normalize_code
from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR
from midday.feeds_fingerprint import (
    baseline_for_day,
    decide_feeds_status,
    diff_vs_baseline,
    save_baseline,
    update_baseline_entry,
)

_DIGEST_DIR = DATA_DIR / "ai_digest"
_REUSE_REASON = "NO_NEW_ANNOUNCEMENT_OR_NEWS"
_FEED_KEYS = ("公告", "资讯", "观点", "研报", "行业资讯")


def _digest_path(day: date, code: str) -> Path:
    return _DIGEST_DIR / day.isoformat() / f"stock_{code}.json"


def _load_digest(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _build_user_prompt(code: str, name: str, feeds: dict, stance: str, groups: list[str]) -> str:
    content_max = int(midday_cfg().get("feeds_digest_content_max") or 280)
    lines = [f"code={code} name={name} stance={stance} groups={','.join(groups)}"]
    for cat in _FEED_KEYS:
        for item in feeds.get(cat) or []:
            title = item.get("title", "")
            pd = item.get("pub_date", "")
            content = str(item.get("content") or item.get("extra") or "")
            if len(content) > content_max:
                content = content[:content_max] + "…"
            lines.append(f"[{cat}] {pd} {title} {content}".strip())
    return "\n".join(lines)


def _local_digest(code: str, feeds: dict[str, Any]) -> dict[str, Any]:
    facts: list[str] = []
    for cat in _FEED_KEYS:
        for item in feeds.get(cat) or []:
            facts.append(f"[{cat}]{item.get('title', '')}")
    summary = "；".join(facts[:6]) if facts else "近几日无新公告资讯"
    return {
        "facts": facts[:5],
        "themes": [],
        "risks": [],
        "critical_items": [],
        "event_net": "中性",
        "summary": summary[:200],
        "short_expectation_hint": "",
        "ok": True,
        "model": "local",
        "digested_at": now_iso(),
    }


def _run_one_digest(
    code: str,
    row: dict[str, Any],
    tags: dict[str, Any],
    trade_date: date,
) -> dict[str, Any]:
    feeds = row.get("feeds_merged") or {}
    name = str((row.get("quote") or {}).get("name") or code)
    stance = str(tags.get("primary_stance") or "theme_other")
    groups = list(tags.get("groups") or row.get("groups") or [])
    user = _build_user_prompt(code, name, feeds, stance, groups)
    raw, model, err = chat(
        DIGEST_STOCK_FEEDS_SYSTEM,
        user,
        max_tokens=1500,
        timeout_sec=digest_timeout_sec(),
    )
    if err or not raw:
        local = _local_digest(code, feeds)
        local["digest_error"] = err or "empty_response"
        return local
    parsed = parse_json_blob(raw)
    parsed["ok"] = True
    parsed["model"] = model
    parsed["digested_at"] = now_iso()
    parsed["raw"] = raw
    return parsed


def run_feeds_digest(
    bundle: dict[str, Any],
    tags_by_code: dict[str, Any],
    *,
    trade_date: date,
) -> dict[str, Any]:
    cfg = midday_cfg()
    workers = min(int(cfg.get("feeds_digest_workers") or 4), 16)
    on_fail = str(cfg.get("on_digest_fail") or "degrade")
    prev_bl, today_bl = baseline_for_day(trade_date)
    baseline: dict[str, Any] = {
        "trade_date": trade_date.isoformat(),
        "prev_trade_date": (prev_bl or {}).get("trade_date") or "",
        "codes": dict((today_bl or {}).get("codes") or {}),
    }

    feeds_digest_by_code: dict[str, Any] = {}
    feeds_diff_by_code: dict[str, Any] = {}
    tasks: list[tuple[str, str, dict]] = []

    for code, row in (bundle.get("by_code") or {}).items():
        code = normalize_code(code)
        feeds = row.get("feeds_merged") or {}
        status, fp, meta = decide_feeds_status(
            code,
            feeds,
            trade_date=trade_date,
            today_baseline=today_bl,
            prev_baseline=prev_bl,
        )
        feeds_diff_by_code[code] = diff_vs_baseline(feeds, prev_fp=meta.get("prev_fingerprint"), curr_fp=fp)

        if status == "failed":
            feeds_digest_by_code[code] = {"status": "failed", "ok": False, "fingerprint": fp}
            continue
        if status == "empty":
            empty = _local_digest(code, feeds)
            empty["status"] = "empty"
            empty["fingerprint"] = fp
            feeds_digest_by_code[code] = empty
            update_baseline_entry(
                baseline,
                code,
                fingerprint=fp,
                item_counts_map=meta.get("item_counts") or {},
                digest_trade_date=trade_date.isoformat(),
                source_id=f"stock_{code}",
            )
            path = _digest_path(trade_date, code)
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, json.dumps(empty, ensure_ascii=False, indent=2))
            continue

        if status == "reuse":
            prev_entry = ((prev_bl or {}).get("codes") or {}).get(code) or ((today_bl or {}).get("codes") or {}).get(code) or {}
            digest_day = prev_entry.get("last_digest_trade_date") or trade_date.isoformat()
            cached = _load_digest(_digest_path(date.fromisoformat(str(digest_day)), code))
            if cached and cached.get("ok"):
                rec = {
                    **cached,
                    "status": "reuse",
                    "fingerprint": fp,
                    "prev_fingerprint": meta.get("prev_fingerprint"),
                    "reuse_reason": _REUSE_REASON,
                    "digest_trade_date": digest_day,
                    "context_note": f"今日公告资讯无变化，沿用 {digest_day} digest",
                }
                feeds_digest_by_code[code] = rec
                update_baseline_entry(
                    baseline,
                    code,
                    fingerprint=fp,
                    item_counts_map=meta.get("item_counts") or {},
                    digest_trade_date=digest_day,
                    source_id=f"stock_{code}",
                )
                continue
            status = "refresh"

        tasks.append((code, status, row))

    def _work(item: tuple[str, str, dict]) -> tuple[str, dict[str, Any]]:
        c, st, row = item
        digest = _run_one_digest(c, row, tags_by_code.get(c, {}), trade_date)
        digest["status"] = st
        digest["fingerprint"] = decide_feeds_status(
            c,
            row.get("feeds_merged") or {},
            trade_date=trade_date,
            today_baseline=today_bl,
            prev_baseline=prev_bl,
        )[1]
        return c, digest

    fail_count = 0
    if tasks:
        if workers <= 1:
            results = [_work(t) for t in tasks]
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(_work, tasks))
        for code, digest in results:
            if not digest.get("ok"):
                fail_count += 1
                feeds_digest_by_code[code] = {**digest, "status": "failed"}
                if on_fail == "abort":
                    break
                continue
            path = _digest_path(trade_date, code)
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, json.dumps(digest, ensure_ascii=False, indent=2))
            feeds_digest_by_code[code] = digest
            meta_counts = {}
            feeds = (bundle.get("by_code") or {}).get(code, {}).get("feeds_merged") or {}
            for cat in _FEED_KEYS:
                meta_counts[cat] = len(feeds.get(cat) or [])
            update_baseline_entry(
                baseline,
                code,
                fingerprint=digest.get("fingerprint") or "",
                item_counts_map=meta_counts,
                digest_trade_date=trade_date.isoformat(),
                source_id=f"stock_{code}",
            )

    save_baseline(baseline, trade_date)
    manifest_path = _DIGEST_DIR / trade_date.isoformat() / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "trade_date": trade_date.isoformat(),
        "stages": {"feeds_digests": {"ok_count": sum(1 for v in feeds_digest_by_code.values() if v.get("ok")), "fail_count": fail_count}},
        "entries": [{"kind": "feeds", "source_id": f"stock_{c}", "path": str(_digest_path(trade_date, c))} for c in feeds_digest_by_code],
    }
    atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))

    return {
        "feeds_digest_by_code": feeds_digest_by_code,
        "feeds_diff_by_code": feeds_diff_by_code,
        "baseline_path": str(save_baseline(baseline, trade_date)),
        "manifest_path": str(manifest_path),
        "fail_count": fail_count,
    }


__all__ = ["run_feeds_digest"]
