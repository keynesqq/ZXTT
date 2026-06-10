"""按 code 构建 events_by_code。"""
from __future__ import annotations

from typing import Any

from core.config import events_cfg
from events.match import TIER_LABEL, classify_item

_FEED_CATS = ("公告", "资讯", "观点", "研报", "行业资讯")


def _bucket_key(tier: str) -> str:
    if tier in ("critical_bear", "high_bear", "medium_bear"):
        return "bear"
    return "bull"


def _dedupe(events: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for ev in events:
        key = (ev.get("title"), ev.get("pub_date"), ev.get("tier"))
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
    return out


def _summary_lists(card: dict[str, Any]) -> dict[str, int]:
    counts = {label: 0 for label in TIER_LABEL.values()}
    counts["unverified"] = 0
    for bucket in ("critical_bear", "critical_bull", "bear", "bull"):
        for ev in card.get(bucket, []):
            lbl = str(ev.get("label") or "").split("·")[0]
            if lbl in counts:
                counts[lbl] += 1
            if ev.get("unverified"):
                counts["unverified"] += 1
    return counts


def build_events_by_code(
    bundle: dict[str, Any],
    *,
    feeds_diff_by_code: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """3.3：规则事件索引。"""
    display_max = int(events_cfg().get("display_max") or 3)
    by_code = bundle.get("by_code") or {}
    industry_critical: dict[str, list[dict]] = {}
    result: dict[str, Any] = {}

    for code, row in by_code.items():
        feeds = row.get("feeds_merged") or {}
        name = str((row.get("quote") or {}).get("name") or code)
        industry = str((row.get("feeds_meta") or {}).get("industry") or (row.get("quote") or {}).get("industry") or "")
        ann_titles = {str(a.get("title") or "") for a in feeds.get("公告") or []}
        diff = (feeds_diff_by_code or {}).get(code) or {}
        has_new = bool(diff.get("new_items"))

        card: dict[str, Any] = {
            "critical_bear": [],
            "critical_bull": [],
            "bear": [],
            "bull": [],
        }
        for cat in _FEED_CATS:
            for item in feeds.get(cat) or []:
                has_ann = str(item.get("title") or "") in ann_titles or cat == "公告"
                ev = classify_item(
                    item,
                    category=cat,
                    code=code,
                    name=name,
                    has_recent_ann=has_ann,
                )
                if not ev:
                    continue
                ev["is_new"] = has_new or not feeds_diff_by_code
                bucket = _bucket_key(ev["tier"])
                if ev["tier"].startswith("critical"):
                    card[ev["tier"]].append(ev)
                else:
                    card[bucket].append(ev)
                if cat == "行业资讯" and industry and ev["label"] in ("大利空", "大利好"):
                    industry_critical.setdefault(industry, []).append(ev)

        for lst_key in ("critical_bear", "critical_bull", "bear", "bull"):
            card[lst_key] = _dedupe(card[lst_key])

        if industry and industry in industry_critical:
            for ev in industry_critical[industry]:
                dup = {**ev, "source_type": "行业", "category": "行业资讯"}
                if dup["tier"].startswith("critical"):
                    target = dup["tier"]
                    if not any(x.get("title") == dup["title"] for x in card[target]):
                        card[target].append(dup)

        flat = []
        for k in ("critical_bear", "critical_bull", "bear", "bull"):
            flat.extend(card[k])
        flat.sort(key=lambda x: int(x.get("display_priority") or 99))
        card["display"] = flat[:display_max]
        card["summary"] = _summary_lists(card)
        result[code] = card

    return result


__all__ = ["build_events_by_code"]
