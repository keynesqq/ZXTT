"""财联社固定栏目长文：收评/数据看盘/焦点复盘等（按交易日+发布时间校验）。"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from collect.manifest import record_source
from core.config import market_cfg
from core.io import atomic_write_text
from core.paths import ROOT
from market.cls.request import get_json, get_signed_json, now_ts, ts_iso, web_headers, web_params, web_sign_params

_DETAIL_URL = "https://www.cls.cn/detail/{article_id}"
_LIST_URLS = (
    "https://www.cls.cn/",
    "https://www.cls.cn/finance",
    "https://www.cls.cn/depth",
)

ARTICLE_SLOTS: list[dict[str, Any]] = [
    {
        "key": "daily_review",
        "label": "每日收评",
        "prefixes": ["【每日收评】"],
        "subject_id": 1139,
    },
    {
        "key": "data_watch",
        "label": "数据看盘",
        "prefixes": ["【数据看盘】"],
        "subject_id": 1187,
    },
    {
        "key": "focus_recap",
        "label": "焦点复盘",
        "prefixes": ["【焦点复盘】"],
        "subject_id": 1135,
    },
    {
        "key": "limit_up_analysis",
        "label": "当日涨停分析",
        "prefixes": ["【当日涨停分析】", "【涨停分析】"],
        "contains": ["涨停分析"],
    },
    {
        "key": "sentiment_hot",
        "label": "今日投资舆情热点",
        "prefixes": ["【今日投资舆情热点】", "【投资舆情热点】"],
        "contains": ["投资舆情热点", "今日投资舆情"],
    },
]

_SUBJECT_DISCOVERY_IDS = (1103, 1139, 1135, 1187)
_SUBJECT_RN = 30
_ID_SCAN_RADIUS = 25
_MAX_ID_SCAN = 20
_MAX_GAP_SCAN = 40
_TYPICAL_ARTICLES_AFTER = time(20, 0)


def before_typical_article_publish(
    for_date: date | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    """当日是否尚未到固定栏目通常出齐时间（仅用于提示，不阻止采集）。"""
    d = for_date or date.today()
    now = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    return now.date() == d and now.time() < _TYPICAL_ARTICLES_AFTER


def incomplete_articles_hint(
    for_date: date | None,
    found_count: int,
    expected_count: int | None = None,
    *,
    now: datetime | None = None,
) -> str | None:
    """未满预期篇数且早于通常发布时间时，返回友好提示。"""
    expected = expected_count if expected_count is not None else len(ARTICLE_SLOTS)
    if found_count >= expected:
        return None
    d = for_date or date.today()
    if not before_typical_article_publish(d, now=now):
        return None
    return (
        f"提示：当前早于 {_TYPICAL_ARTICLES_AFTER.strftime('%H:%M')}，"
        f"部分长文可能尚未发布（已找到 {found_count}/{expected}）"
    )


def load_cls_daily_articles(for_date: date | None = None) -> dict[str, Any] | None:
    d = for_date or date.today()
    path = _storage_root() / f"{d.isoformat()}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _candidate_matches_trade_date(item: dict[str, Any], trade_date: date) -> bool:
    ct = item.get("ctime")
    try:
        ts = int(ct) if ct is not None else None
    except (TypeError, ValueError):
        return False
    if ts is None or ts < 1e9:
        return False
    return datetime.fromtimestamp(ts).date() == trade_date


def match_from_candidates(
    candidates: list[dict[str, Any]],
    *,
    trade_date: date,
    slots: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """首页/列表页候选：按标题+发布日匹配，无需逐篇拉详情。"""
    slots = slots or ARTICLE_SLOTS
    best: dict[str, dict[str, Any]] = {}
    for item in candidates:
        if not _candidate_matches_trade_date(item, trade_date):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        try:
            pub_ts = int(item["ctime"])
        except (TypeError, ValueError, KeyError):
            continue
        for slot in slots:
            key = slot["key"]
            if not _match_slot(title, slot, trade_date=trade_date):
                continue
            rec = {
                "id": str(item["id"]),
                "title": title,
                "published_ts": pub_ts,
                "published_at": ts_iso(pub_ts),
                "trade_date": trade_date.isoformat(),
            }
            prev = best.get(key)
            if not prev or pub_ts > (prev.get("published_ts") or 0):
                best[key] = rec
    return best


def _subject_ids_to_fetch() -> tuple[int, ...]:
    ids: list[int] = list(_SUBJECT_DISCOVERY_IDS)
    for slot in ARTICLE_SLOTS:
        sid = slot.get("subject_id")
        if sid and int(sid) not in ids:
            ids.append(int(sid))
    return tuple(ids)


def fetch_subject_rows(subject_id: int, *, rn: int = _SUBJECT_RN) -> list[dict[str, Any]]:
    """栏目 API：一次返回该话题下最近 N 篇。"""
    url = f"https://www.cls.cn/api/subject/{subject_id}/article"
    params = web_sign_params(Subject_Id=subject_id, rn=rn)
    data = get_signed_json(
        url,
        params=params,
        referer=f"https://www.cls.cn/subject/{subject_id}",
        timeout=10.0,
    )
    if not isinstance(data, dict):
        return []
    rows = data.get("data")
    return rows if isinstance(rows, list) else []


def subject_rows_to_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        aid = row.get("article_id") or row.get("id")
        title = row.get("article_title") or row.get("title")
        ct = row.get("article_time") or row.get("ctime")
        if not aid or not title:
            continue
        out.append(
            {
                "id": str(aid),
                "title": str(title).strip(),
                "ctime": ct,
                "source": "subject_api",
            }
        )
    return out


def discover_subject_candidates() -> list[dict[str, Any]]:
    """并行拉盘面直播 + 各固定栏目话题，秒级补齐五篇候选。"""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    sids = _subject_ids_to_fetch()
    workers = min(4, len(sids))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_subject_rows, sid): sid for sid in sids}
        for fut in as_completed(futures):
            try:
                rows = fut.result()
            except Exception:
                continue
            for item in subject_rows_to_candidates(rows):
                aid = item["id"]
                if aid in seen:
                    continue
                seen.add(aid)
                out.append(item)
    return out


def discover_all_candidates(*, trade_date: date) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for item in discover_subject_candidates() + discover_article_candidates(trade_date=trade_date):
        aid = str(item.get("id") or "")
        if not aid or aid in seen:
            continue
        seen.add(aid)
        merged.append(item)
    return merged


def discover_matched_articles(
    trade_date: date,
    *,
    id_scan: bool = True,
    use_ai: bool = False,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """栏目 API 优先；仅缺篇时做小范围 ID 补扫（默认不用 AI）。"""
    warnings: list[str] = []
    candidates = discover_all_candidates(trade_date=trade_date)
    matched = match_from_candidates(candidates, trade_date=trade_date)

    if id_scan and len(matched) < len(ARTICLE_SLOTS):
        scan_ids = _ids_to_scan(candidates, trade_date)
        extra = scan_article_ids(
            scan_ids,
            trade_date=trade_date,
            max_scans=min(len(scan_ids), _MAX_ID_SCAN),
            stop_when_complete=True,
        )
        for k, v in extra.items():
            if k not in matched or (v.get("published_ts") or 0) > (matched[k].get("published_ts") or 0):
                matched[k] = v

    if use_ai and len(matched) < len(ARTICLE_SLOTS):
        from market.cls.daily_ai import _pool_from_candidates, ai_match_slots

        pool = _pool_from_candidates(candidates, trade_date)
        ai_hits = ai_match_slots(pool, trade_date=trade_date)
        if "_error" in ai_hits:
            warnings.append(f"AI 匹配: {ai_hits['_error']['message']}")
        else:
            for k, v in ai_hits.items():
                if k not in matched or (v.get("published_ts") or 0) > (matched[k].get("published_ts") or 0):
                    matched[k] = v

    return matched, warnings


def _fetch_matched_contents(
    matched: dict[str, dict[str, Any]],
    *,
    trade_date: date,
) -> dict[str, dict[str, Any]]:
    """并行拉五篇正文，避免串行卡住。"""
    out = dict(matched)
    pending = [(k, v) for k, v in matched.items() if not v.get("content")]
    if not pending:
        return out

    def _one(pair: tuple[str, dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
        key, rec = pair
        full = fetch_article_detail(rec["id"], trade_date=trade_date, content=True, timeout=10.0)
        return key, full

    with ThreadPoolExecutor(max_workers=min(5, len(pending))) as pool:
        for key, full in pool.map(_one, pending):
            if full:
                out[key] = full
    return out


def _seed_id_range(candidates: list[dict[str, Any]]) -> list[int]:
    seeds: list[int] = []
    for c in candidates:
        try:
            seeds.append(int(c["id"]))
        except (TypeError, ValueError):
            pass
    if not seeds:
        return []
    hi = max(seeds) + 5
    lo = max(hi - _ID_SCAN_RADIUS, min(seeds) - 5)
    return list(range(hi, lo - 1, -1))


def _ids_to_scan(candidates: list[dict[str, Any]], trade_date: date) -> list[int]:
    """当日候选 ID 扫描：午盘栏目（涨停分析/舆情）id 常低于收评，需向下多扫一段。"""
    today_ids: list[int] = []
    for c in candidates:
        if not _candidate_matches_trade_date(c, trade_date):
            continue
        try:
            today_ids.append(int(c["id"]))
        except (TypeError, ValueError):
            pass
    if today_ids:
        lo, hi = min(today_ids), max(today_ids)
        half = _MAX_GAP_SCAN // 2
        bands = [
            range(hi + 3, max(hi - half, lo), -1),
            range(lo + 5, max(lo - half, 1), -1),
        ]
        out: list[int] = []
        seen: set[int] = set()
        for band in bands:
            for aid in band:
                if aid in seen:
                    continue
                seen.add(aid)
                out.append(aid)
                if len(out) >= _MAX_GAP_SCAN:
                    return out
        return out
    return _seed_id_range(candidates)[:_MAX_ID_SCAN]


def _storage_root() -> Path:
    return ROOT / "data" / "cls_articles"


def _match_slot(title: str, slot: dict[str, Any], *, trade_date: date | None = None) -> bool:
    title = title.strip()
    for p in slot.get("prefixes") or []:
        if title.startswith(p):
            return True
    key = slot.get("key")
    if trade_date and key == "limit_up_analysis":
        dated = f"{trade_date.month}月{trade_date.day}日涨停分析"
        if title == dated or title.startswith(dated):
            return True
    if key == "sentiment_hot" and title.startswith("今日投资舆情热点"):
        return True
    for frag in slot.get("contains") or []:
        if frag in title and title.startswith("【"):
            if key == "limit_up_analysis" and title.startswith("【VIP】"):
                continue
            return True
    return False


def _strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _walk_next_articles(page_props: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            title = str(o.get("title") or o.get("name") or "").strip()
            aid = o.get("id") or o.get("article_id") or o.get("articleId")
            ctime = o.get("ctime") or o.get("article_time") or o.get("time")
            if aid and title and len(title) >= 4:
                found.append({"id": str(aid), "title": title, "ctime": ctime})
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(page_props)
    return found


def discover_article_candidates(*, trade_date: date) -> list[dict[str, Any]]:
    """从首页/看盘页 Next.js 数据发现候选文章（请求带 _t）。"""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for url in _LIST_URLS:
        html = get_json(url, params=web_params(), headers=web_headers(referer=url), timeout=20)
        if not isinstance(html, str):
            continue
        m = re.search(r"__NEXT_DATA__.*?>({.*?})</script>", html, re.S)
        if not m:
            continue
        pp = json.loads(m.group(1)).get("props", {}).get("pageProps", {})
        for item in _walk_next_articles(pp):
            aid = item["id"]
            if aid in seen:
                continue
            seen.add(aid)
            out.append({**item, "source_page": url})
    return out


def scan_article_ids(
    article_ids: list[int],
    *,
    trade_date: date,
    slots: list[dict[str, Any]] | None = None,
    stop_when_complete: bool = True,
    max_scans: int | None = None,
) -> dict[str, dict[str, Any]]:
    """按 ID 拉详情，匹配固定栏目且发布日在 trade_date；找齐或达上限即停。"""
    slots = slots or ARTICLE_SLOTS
    best: dict[str, dict[str, Any]] = {}
    scanned = 0
    limit = max_scans if max_scans is not None else _MAX_ID_SCAN

    for aid in article_ids:
        if stop_when_complete and len(best) >= len(slots):
            break
        if scanned >= limit:
            break
        scanned += 1
        try:
            meta = fetch_article_detail(str(aid), trade_date=trade_date, content=False, timeout=8.0)
        except Exception:
            continue
        if not meta:
            continue
        title = meta.get("title") or ""
        pub = meta.get("published_ts") or 0
        for slot in slots:
            key = slot["key"]
            if not _match_slot(title, slot, trade_date=trade_date):
                continue
            prev = best.get(key)
            if not prev or pub > (prev.get("published_ts") or 0):
                best[key] = meta
    return best


def fetch_article_detail(
    article_id: str,
    *,
    trade_date: date | None = None,
    content: bool = True,
    timeout: float = 15.0,
) -> dict[str, Any] | None:
    """拉取单篇详情；返回发布时间戳与正文。"""
    requested_at = now_ts()
    html = get_json(
        _DETAIL_URL.format(article_id=article_id),
        params=web_params(),
        headers=web_headers(referer=f"https://www.cls.cn/detail/{article_id}"),
        timeout=timeout,
    )
    if not isinstance(html, str):
        return None
    m = re.search(r"__NEXT_DATA__.*?>({.*?})</script>", html, re.S)
    if not m:
        return None
    art = json.loads(m.group(1)).get("props", {}).get("pageProps", {}).get("articleDetail") or {}
    if not art.get("title"):
        return None
    pub_ts = art.get("ctime") or art.get("time")
    try:
        pub_ts = int(pub_ts) if pub_ts is not None else None
    except (TypeError, ValueError):
        pub_ts = None

    d = trade_date or date.today()
    if pub_ts is not None:
        pub_date = datetime.fromtimestamp(pub_ts).date()
        if pub_date != d:
            return None

    body_raw = str(art.get("content") or art.get("content_detail") or "")
    payload: dict[str, Any] = {
        "id": str(article_id),
        "title": str(art.get("title") or "").strip(),
        "published_ts": pub_ts,
        "published_at": ts_iso(pub_ts),
        "trade_date": d.isoformat(),
        "requested_at": requested_at,
        "requested_at_iso": ts_iso(requested_at),
        "url": f"https://www.cls.cn/detail/{article_id}",
        "author": (art.get("author") or {}).get("name") if isinstance(art.get("author"), dict) else art.get("author"),
    }
    if content:
        payload["content"] = _strip_html(body_raw)
        payload["content_chars"] = len(payload["content"])
    return payload


def collect_cls_daily_articles(
    *,
    for_date: date | None = None,
    calendar_date: date | None = None,
    fetch_content: bool = True,
    id_scan: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """采集五篇固定栏目；仅保留发布日=交易日的文章。"""
    d = for_date or date.today()
    cal = calendar_date or d
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.date() < d:
        cached = load_cls_daily_articles(d)
        if cached and cached.get("articles"):
            return cached
        return {
            "source": "cls.cn",
            "trade_date": d.isoformat(),
            "collected_at": now_ts(),
            "collected_at_iso": ts_iso(now_ts()),
            "skipped": True,
            "skip_reason": f"未到 {d.isoformat()}，固定栏目尚未发布",
            "articles": {},
            "found_count": 0,
            "expected_count": len(ARTICLE_SLOTS),
        }

    if not force:
        cached = load_cls_daily_articles(d)
        if cached and cached.get("articles") and not cached.get("skipped"):
            if int(cached.get("found_count") or 0) >= len(ARTICLE_SLOTS):
                return cached

    collected_at = now_ts()
    use_ai = bool(market_cfg().get("cls_articles_use_ai", False))
    matched, warnings = discover_matched_articles(d, id_scan=id_scan, use_ai=use_ai)
    if fetch_content:
        matched = _fetch_matched_contents(matched, trade_date=d)

    articles: dict[str, Any] = {}
    for slot in ARTICLE_SLOTS:
        key = slot["key"]
        rec = matched.get(key)
        if not rec:
            warnings.append(f"{slot['label']}: 未找到 {d.isoformat()} 当日文章")
            continue
        if fetch_content and not rec.get("content"):
            warnings.append(f"{slot['label']}: 正文拉取失败或日期不符")
            continue
        articles[key] = {
            "label": slot["label"],
            **rec,
        }

    hint = incomplete_articles_hint(d, len(articles), len(ARTICLE_SLOTS), now=now)
    if hint:
        warnings.insert(0, hint)

    payload: dict[str, Any] = {
        "source": "cls.cn",
        "trade_date": d.isoformat(),
        "collected_at": collected_at,
        "collected_at_iso": ts_iso(collected_at),
        "request_ts": now_ts(),
        "before_typical_publish": before_typical_article_publish(d, now=now),
        "articles": articles,
        "found_count": len(articles),
        "expected_count": len(ARTICLE_SLOTS),
    }
    if warnings:
        payload["warnings"] = warnings

    root = _storage_root()
    root.mkdir(parents=True, exist_ok=True)
    out_path = root / f"{d.isoformat()}.json"
    save = {**payload}
    if not fetch_content:
        save = json.loads(json.dumps(save, ensure_ascii=False))
    atomic_write_text(out_path, json.dumps(save, ensure_ascii=False, indent=2))

    record_source(
        d,
        "cls_articles",
        {
            "ok": len(articles) >= len(ARTICLE_SLOTS),
            "found_count": len(articles),
            "expected_count": len(ARTICLE_SLOTS),
            "skipped": False,
            "forced": force,
        },
        calendar_date=cal,
    )
    return payload


def format_cls_articles_prompt(data: dict[str, Any] | None) -> list[str]:
    if not data:
        return []
    if data.get("skipped"):
        return []
    if not data.get("articles"):
        return []
    lines = [
        "",
        "## [财联社固定栏目] 定性参考（带发布时间）",
        f"- 交易日: {data.get('trade_date', '—')} · 采集: {data.get('collected_at_iso', '—')}",
    ]
    for slot in ARTICLE_SLOTS:
        art = (data.get("articles") or {}).get(slot["key"])
        if not art:
            lines.append(f"- {slot['label']}: （未采集到当日文章）")
            continue
        body = str(art.get("content") or "")
        excerpt = body[:1200] + ("…" if len(body) > 1200 else "")
        lines.append(f"### {slot['label']} · {art.get('published_at', '—')}")
        lines.append(f"标题: {art.get('title', '—')}")
        if excerpt:
            lines.append(excerpt)
    for w in data.get("warnings") or []:
        lines.append(f"- ⚠ {w}")
    lines.append("- 解读要求: 仅引用上述已标注发布时间的当日栏目，勿编造未提供的收评/复盘内容。")
    return lines
