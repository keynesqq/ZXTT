"""财联社五篇固定栏目：并行拉候选 + AI 按规则匹配（补全首页抓不到的午盘栏目）。"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any

from ai.llm import chat
from core.config import market_cfg
from market.cls.daily_articles import (
    ARTICLE_SLOTS,
    _candidate_matches_trade_date,
    _ids_to_scan,
    _match_slot,
    fetch_article_detail,
    match_from_candidates,
)
from market.cls.request import ts_iso

_SYSTEM = """你是财联社固定栏目匹配器。根据候选文章列表，为每个栏目选出唯一一篇。

栏目与标题规则（发布日必须等于 trade_date）：
- daily_review：标题以【每日收评】开头
- data_watch：标题以【数据看盘】开头
- focus_recap：标题以【焦点复盘】开头
- limit_up_analysis：标题为「M月D日涨停分析」或以【当日涨停分析】/【涨停分析】开头
- sentiment_hot：标题为「今日投资舆情热点」或以【今日投资舆情热点】/【投资舆情热点】开头

只输出 JSON 对象，键为栏目 key，值为文章 id 字符串。找不到的 key 不要出现。不要 markdown、不要解释。"""


def _id_scan_workers() -> int:
    try:
        return max(1, min(8, int(market_cfg().get("cls_articles_id_scan_workers") or 6)))
    except (TypeError, ValueError):
        return 6


def _use_ai_matcher() -> bool:
    return bool(market_cfg().get("cls_articles_use_ai", False))


def _pool_from_candidates(candidates: list[dict[str, Any]], trade_date: date) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in candidates:
        if not _candidate_matches_trade_date(item, trade_date):
            continue
        aid = str(item.get("id") or "")
        if not aid or aid in seen:
            continue
        seen.add(aid)
        out.append(
            {
                "id": aid,
                "title": str(item.get("title") or "").strip(),
                "published_ts": int(item.get("ctime") or item.get("published_ts") or 0),
            }
        )
    return out


def scan_metadata_parallel(
    article_ids: list[int],
    *,
    trade_date: date,
    max_scans: int | None = None,
    workers: int | None = None,
) -> list[dict[str, Any]]:
    """并行拉详情元数据（无正文），返回当日候选列表。"""
    limit = max_scans if max_scans is not None else len(article_ids)
    ids = article_ids[:limit]
    workers = workers or _id_scan_workers()
    found: list[dict[str, Any]] = []

    def _one(aid: int) -> dict[str, Any] | None:
        meta = fetch_article_detail(str(aid), trade_date=trade_date, content=False, timeout=6.0)
        if not meta:
            return None
        return {
            "id": meta["id"],
            "title": meta.get("title") or "",
            "ctime": meta.get("published_ts"),
            "published_ts": meta.get("published_ts"),
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, aid) for aid in ids]
        for fut in as_completed(futures):
            try:
                row = fut.result()
            except Exception:
                continue
            if row:
                found.append(row)
    return found


def _parse_ai_mapping(text: str) -> dict[str, str]:
    text = text.strip()
    if not text:
        return {}
    block = text
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        block = m.group(1)
    else:
        start, end = block.find("{"), block.rfind("}")
        if start >= 0 and end > start:
            block = block[start : end + 1]
    try:
        data = json.loads(block)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in data.items():
        key = str(k).strip()
        if key and v is not None:
            out[key] = str(v).strip()
    return out


def ai_match_slots(
    pool: list[dict[str, Any]],
    *,
    trade_date: date,
) -> dict[str, dict[str, Any]]:
    """把候选池交给 LLM，返回 slot_key -> 元数据。"""
    if not pool:
        return {}
    lines = []
    for row in sorted(pool, key=lambda x: -(x.get("published_ts") or 0)):
        lines.append(
            f"id={row['id']}\ttitle={row.get('title')}\tpublished_ts={row.get('published_ts')}"
        )
    user = f"trade_date={trade_date.isoformat()}\n\n候选（共{len(lines)}篇）:\n" + "\n".join(lines)
    content, _model, err = chat(_SYSTEM, user, max_tokens=400)
    if err:
        return {"_error": {"message": err}}
    mapping = _parse_ai_mapping(content)
    best: dict[str, dict[str, Any]] = {}
    pool_by_id = {str(r["id"]): r for r in pool}
    for slot in ARTICLE_SLOTS:
        key = slot["key"]
        aid = mapping.get(key)
        if not aid or aid not in pool_by_id:
            continue
        row = pool_by_id[aid]
        title = row.get("title") or ""
        if not _match_slot(title, slot, trade_date=trade_date):
            if key == "limit_up_analysis" and title == f"{trade_date.month}月{trade_date.day}日涨停分析":
                pass
            elif key == "sentiment_hot" and title.startswith("今日投资舆情热点"):
                pass
            else:
                continue
        pub_ts = int(row.get("published_ts") or 0)
        best[key] = {
            "id": aid,
            "title": title,
            "published_ts": pub_ts,
            "published_at": ts_iso(pub_ts),
            "trade_date": trade_date.isoformat(),
        }
    return best


def discover_with_ai(
    *,
    trade_date: date,
    homepage_candidates: list[dict[str, Any]] | None = None,
    id_scan: bool = True,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """首页匹配 + 并行 ID 元数据扫描 + AI 补全。返回 (matched, warnings)。"""
    warnings: list[str] = []
    candidates = homepage_candidates or []
    matched = match_from_candidates(candidates, trade_date=trade_date)
    pool = _pool_from_candidates(candidates, trade_date)

    if id_scan and len(matched) < len(ARTICLE_SLOTS):
        scan_ids = _ids_to_scan(candidates, trade_date)
        meta_rows = scan_metadata_parallel(scan_ids, trade_date=trade_date)
        for row in meta_rows:
            aid = str(row["id"])
            if aid not in {p["id"] for p in pool}:
                pool.append(row)
        extra = match_from_candidates(pool, trade_date=trade_date)
        for k, v in extra.items():
            if k not in matched or (v.get("published_ts") or 0) > (matched[k].get("published_ts") or 0):
                matched[k] = v

    if len(matched) < len(ARTICLE_SLOTS) and _use_ai_matcher():
        ai_hits = ai_match_slots(pool, trade_date=trade_date)
        if "_error" in ai_hits:
            warnings.append(f"AI 匹配: {ai_hits['_error']['message']}")
        else:
            for k, v in ai_hits.items():
                if k not in matched or (v.get("published_ts") or 0) > (matched[k].get("published_ts") or 0):
                    matched[k] = v

    return matched, warnings
