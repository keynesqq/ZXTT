"""事件 tier 匹配与中文 label。"""
from __future__ import annotations

from core.config import events_cfg
from feeds.news_filter import news_matches_stock

DEFAULT_EVENTS = {
    "critical_bear": [
        "退市", "*ST", "立案", "调查", "重大违法", "财务造假", "造假",
        "债务违约", "破产", "预亏", "业绩暴雷", "修正向下",
        "强制措施", "无法表示意见", "否定意见",
    ],
    "critical_bull": [
        "业绩预增", "扭亏为盈", "重大合同", "重大中标", "资产重组通过",
        "资产注入", "大幅预增", "上调至买入", "首推", "重大许可",
    ],
    "high_bear": ["减持", "质押", "问询函", "关注函", "诉讼", "仲裁", "预减", "下滑"],
    "high_bull": ["回购", "增持", "政策支持", "获批", "量产", "订单大增"],
    "medium_bear": ["亏损", "下滑", "风险", "警示"],
    "medium_bull": ["增长", "突破", "合作", "签约"],
}

TIER_LABEL = {
    "critical_bear": "大利空",
    "critical_bull": "大利好",
    "high_bear": "利空",
    "high_bull": "利好",
    "medium_bear": "轻空",
    "medium_bull": "轻多",
}

DISPLAY_PRIORITY = {
    "critical_bear": 10,
    "critical_bull": 10,
    "high_bear": 30,
    "high_bull": 30,
    "medium_bear": 50,
    "medium_bull": 50,
}

_TIER_ORDER = (
    "critical_bear",
    "critical_bull",
    "high_bear",
    "high_bull",
    "medium_bear",
    "medium_bull",
)


def _keywords() -> dict[str, list[str]]:
    cfg = events_cfg()
    out = {k: list(v) for k, v in DEFAULT_EVENTS.items()}
    if not cfg.get("enable_medium", True):
        out["medium_bear"] = []
        out["medium_bull"] = []
    for key in DEFAULT_EVENTS:
        if cfg.get(key):
            out[key] = [str(x) for x in cfg[key]]
    for tier, words in out.items():
        out[tier] = sorted(words, key=len, reverse=True)
    return out


def _st_boundary_match(text: str, kw: str) -> bool:
    if kw not in ("ST", "*ST"):
        return kw in text
    if "*ST" in text:
        return kw == "*ST"
    if kw == "ST":
        return text.startswith("ST") or " ST" in text or "退市" in text
    return False


def match_tier(title: str) -> str | None:
    text = title or ""
    keywords = _keywords()
    best: str | None = None
    best_rank = 99
    for i, tier in enumerate(_TIER_ORDER):
        for kw in keywords.get(tier, []):
            if not kw:
                continue
            hit = _st_boundary_match(text, kw) if kw in ("ST", "*ST") else kw in text
            if hit and i < best_rank:
                best = tier
                best_rank = i
                break
    return best


def classify_item(
    item: dict,
    *,
    category: str,
    code: str,
    name: str,
    has_recent_ann: bool,
) -> dict | None:
    title = str(item.get("title") or "")
    if category in ("资讯", "观点") and code:
        if not news_matches_stock(title, code, name):
            return None
    tier = match_tier(title)
    if not tier:
        return None
    unverified = category != "公告" and tier.startswith("critical") and not has_recent_ann
    if "减持" in title and category != "公告":
        tier = "high_bear"
        unverified = False
    label = TIER_LABEL[tier]
    if unverified:
        label = f"{label}·待核实"
    direction = "bear" if "bear" in tier else "bull"
    return {
        "tier": tier,
        "label": label,
        "direction": direction,
        "title": title,
        "pub_date": str(item.get("pub_date") or ""),
        "category": category,
        "source_type": _source_type(category),
        "unverified": unverified,
        "display_priority": DISPLAY_PRIORITY[tier],
    }


def _source_type(category: str) -> str:
    if category == "公告":
        return "事件"
    if category == "行业资讯":
        return "行业"
    if category == "观点":
        return "观点"
    if category == "研报":
        return "研报"
    return "舆情"


__all__ = ["match_tier", "classify_item", "TIER_LABEL", "DISPLAY_PRIORITY"]
