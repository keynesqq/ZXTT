"""第 3 步 3.4 · 快照标签与 primary_stance。"""
from __future__ import annotations

from typing import Any

from core.config import tags_cfg

_GROUP_STANCE = {
    "我的": ("holding", "持仓"),
    "想买的": ("candidate", "候选"),
    "跌幅达到预期重点关注": ("watch_right", "观察"),
}
_STANCE_PRIORITY = ("holding", "candidate", "watch_right", "theme_other")


def _primary_stance(groups: list[str]) -> tuple[str, str]:
    best = "theme_other"
    best_rank = 99
    label = "其它"
    for g in groups:
        stance, lbl = _GROUP_STANCE.get(g, ("theme_other", "其它"))
        rank = _STANCE_PRIORITY.index(stance) if stance in _STANCE_PRIORITY else 99
        if rank < best_rank:
            best = stance
            best_rank = rank
            label = lbl
    return best, label


def _trend_short(pct: float | None, pct_5d: float | None) -> str:
    if pct is not None and pct <= -5:
        return "弱"
    if pct_5d is not None and pct_5d <= -10:
        return "弱"
    if pct is not None and pct >= 3 and (pct_5d or 0) > 0:
        return "强"
    return "中"


def _trend_mid(pct_20d: float | None, ma20_dist: float | None) -> str:
    if pct_20d is not None and pct_20d <= -10:
        return "弱"
    if ma20_dist is not None and ma20_dist <= -5:
        return "弱"
    if pct_20d is not None and pct_20d >= 15 and (ma20_dist or 0) > 0:
        return "强"
    return "中"


def _pool_tags(code: str, sentiment: dict | None) -> list[str]:
    if not sentiment:
        return []
    tags: list[str] = []
    for pool_key, label in (
        ("limit_up_index", "在涨停池"),
        ("prev_limit_index", "在昨涨停"),
        ("broken_limit_index", "曾炸板"),
    ):
        index = sentiment.get(pool_key) or {}
        if code in {str(c) for c in index.keys()}:
            tags.append(label)
    return tags


def build_tags_by_code(bundle: dict[str, Any]) -> dict[str, Any]:
    cfg = tags_cfg()
    max_tags = int(cfg.get("max_display_tags") or 5)
    sentiment = (bundle.get("market") or {}).get("sentiment") or {}
    out: dict[str, Any] = {}

    for code, row in (bundle.get("by_code") or {}).items():
        quote = row.get("quote") or {}
        flow = row.get("flow_stock") or {}
        groups = list(row.get("groups") or [])
        primary_stance, stance_label = _primary_stance(groups)

        pct = quote.get("pct_chg")
        pct_5d = quote.get("pct_5d")
        pct_20d = quote.get("pct_20d")
        ma20_dist = quote.get("ma20_dist")
        amount_yi = quote.get("amount_yi") or 0
        main_net = flow.get("main_net_yi")
        ratio = abs(main_net) / amount_yi if amount_yi and main_net is not None else None

        tags: list[str] = []
        limit_status = str(quote.get("limit_status") or "正常")
        if limit_status != "正常":
            tags.append(limit_status)

        if pct is not None:
            if pct <= cfg.get("pct_drop_heavy", -7):
                tags.append("单日大跌")
            elif pct <= cfg.get("pct_drop_mild", -5):
                tags.append("偏弱")
            elif pct >= cfg.get("pct_rise_heavy", 7):
                tags.append("大涨")

        if ratio is not None:
            heavy = cfg.get("main_net_ratio_heavy", 0.15)
            mild = cfg.get("main_net_ratio_mild", 0.05)
            if main_net is not None and main_net < 0:
                if ratio >= heavy:
                    tags.append("主力大幅流出")
                elif ratio >= mild:
                    tags.append("主力流出")
            elif main_net is not None and main_net > 0:
                if ratio >= heavy:
                    tags.append("主力大幅流入")
                elif ratio >= mild:
                    tags.append("主力流入")

        if pct is not None and main_net is not None:
            if pct > 0 and main_net < 0:
                tags.append("价涨资出")
            elif pct < 0 and main_net > 0:
                tags.append("价跌资进")

        ts = _trend_short(pct, pct_5d)
        tm = _trend_mid(pct_20d, ma20_dist)
        if ts == "弱":
            tags.append("短线弱")
        elif ts == "强":
            tags.append("短线强")
        if tm == "弱":
            tags.append("中期弱")
        elif tm == "强":
            tags.append("中期强")

        ar = quote.get("amount_ratio")
        if ar is not None:
            if ar < cfg.get("amount_ratio_shrink", 0.7):
                tags.append("缩量")
            elif ar > cfg.get("amount_ratio_expand", 1.3):
                tags.append("放量")

        shape = str((row.get("intraday_full") or {}).get("session_shape") or "").strip()
        if shape:
            tags.append(f"形态:{shape}")

        tags.extend(_pool_tags(code, sentiment))
        tags = tags[:max_tags]

        out[code] = {
            "code": code,
            "groups": groups,
            "primary_stance": primary_stance,
            "stance_label": stance_label,
            "trend_short": ts,
            "trend_mid": tm,
            "tags": tags,
            "pool_tags": _pool_tags(code, sentiment),
            "tag_facts": {
                "pct_chg": pct,
                "pct_5d": pct_5d,
                "pct_20d": pct_20d,
                "ma20_dist": ma20_dist,
                "amount_ratio": ar,
                "main_net_yi": main_net,
                "main_net_ratio": round(ratio, 4) if ratio is not None else None,
                "limit_status": limit_status,
                "intraday_shape": shape,
            },
        }
    return out


__all__ = ["build_tags_by_code"]
