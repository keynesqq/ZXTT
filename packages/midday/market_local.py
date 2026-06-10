"""第 3 步 3.5 · 大盘本地 L1/L2（午间上午盘语义）。"""
from __future__ import annotations

from typing import Any


def _norm_industry(name: str) -> str:
    return (name or "").replace(" ", "").lower()


def _match_industry(industry: str, target: str) -> tuple[bool, str]:
    a, b = _norm_industry(industry), _norm_industry(target)
    if not a or not b:
        return False, "none"
    if a == b:
        return True, "exact"
    if a in b or b in a:
        return True, "contains"
    return False, "none"


def _index_row(indices: list[dict], symbol: str) -> dict:
    for row in indices:
        if str(row.get("symbol") or "") == symbol:
            return row
    return {}


def build_market_local(bundle: dict[str, Any], health: dict[str, Any]) -> dict[str, Any]:
    market = bundle.get("market") or {}
    sentiment = market.get("sentiment") or {}
    cls_fin = market.get("cls_finance") or {}
    indices = (market.get("index") or {}).get("indices") or []
    flow_meta = market.get("flow_meta") or {}
    trust = health.get("trust_flags") or {}
    by_code = bundle.get("by_code") or {}

    sh = _index_row(indices, "sh000001")
    cy = _index_row(indices, "sz399006")
    index_note = ""
    if sh.get("pct_chg") is not None and cy.get("pct_chg") is not None:
        if abs(float(sh["pct_chg"]) - float(cy["pct_chg"])) >= 1.5:
            index_note = "指数分化"

    north = flow_meta.get("northbound") or {}
    mkt = flow_meta.get("market") or {}
    main_available = bool(trust.get("market_main_flow"))
    flow_ref = main_available and not trust.get("northbound_suspicious")

    wl_rows = []
    for code, row in by_code.items():
        fs = row.get("flow_stock") or {}
        net = fs.get("main_net_yi")
        if net is None:
            continue
        wl_rows.append(
            {
                "code": code,
                "name": (row.get("quote") or {}).get("name", code),
                "main_net_yi": net,
            }
        )
    wl_rows.sort(key=lambda x: float(x.get("main_net_yi") or 0), reverse=True)
    total_net = sum(float(r.get("main_net_yi") or 0) for r in wl_rows)
    wl_summary = {
        "total_net_yi": round(total_net, 4),
        "inflow_count": sum(1 for r in wl_rows if (r.get("main_net_yi") or 0) > 0),
        "outflow_count": sum(1 for r in wl_rows if (r.get("main_net_yi") or 0) < 0),
        "top_inflow": wl_rows[:3],
        "top_outflow": list(reversed(wl_rows[-3:])),
    }

    crosscheck: list[dict[str, Any]] = []
    sent_up = sentiment.get("limit_up_count")
    cls_up = cls_fin.get("limit_up_cls") or cls_fin.get("limit_up_count")
    if sent_up is not None and cls_up is not None and abs(int(sent_up) - int(cls_up)) >= 3:
        crosscheck.append({"code_key": "LIMIT_COUNT_GAP", "level": "info", "message": f"涨停家数差 {sent_up} vs {cls_up}"})
    pool_sig = str(sentiment.get("pool_signal") or "")
    heat = cls_fin.get("market_heat")
    if heat is not None:
        h = float(heat)
        if pool_sig in ("中", "强") and h < 35:
            crosscheck.append({"code_key": "POOL_CLS_DIVERGE", "level": "info", "message": f"池子{pool_sig} vs 热度{h}"})
        elif pool_sig == "弱" and h > 60:
            crosscheck.append({"code_key": "POOL_CLS_DIVERGE", "level": "info", "message": f"池子弱 vs 热度{h}"})

    mainlines = []
    ml = cls_fin.get("mainline") or {}
    for line in ml.get("lines") or []:
        if isinstance(line, dict):
            mainlines.append(
                {
                    "name": line.get("name") or line.get("title") or "",
                    "desc_short": str(line.get("desc") or line.get("summary") or "")[:80],
                    "plates": line.get("plates") or [],
                    "source": "cls_mainline",
                }
            )
    wind_plates = []
    for wp in cls_fin.get("wind_plates") or []:
        if isinstance(wp, dict):
            wind_plates.append(
                {
                    "name": wp.get("name") or "",
                    "catalyst_short": str(wp.get("reason") or wp.get("catalyst") or "")[:80],
                    "source": "cls_wind",
                }
            )
    hot_industries = []
    for hi in sentiment.get("hot_industries") or []:
        if isinstance(hi, dict):
            hot_industries.append(
                {
                    "name": hi.get("name") or "",
                    "limit_up_count": hi.get("limit_up_count"),
                    "source": "akshare_pool",
                }
            )

    industry_in_hot: dict[str, Any] = {}
    l2_names: list[tuple[str, str]] = []
    for hi in hot_industries:
        l2_names.append((hi["name"], "hot_industries"))
    for wp in wind_plates:
        l2_names.append((wp["name"], "wind_plates"))
    for ml_row in mainlines:
        for p in ml_row.get("plates") or []:
            pname = p.get("name") if isinstance(p, dict) else str(p)
            if pname:
                l2_names.append((pname, "mainline"))

    for code, row in by_code.items():
        industry = str((row.get("quote") or {}).get("industry") or "")
        sources: list[str] = []
        level = "none"
        for target, src in l2_names:
            hit, lv = _match_industry(industry, target)
            if hit:
                sources.append(src)
                if lv == "exact" or level == "none":
                    level = lv
        industry_in_hot[code] = {
            "in_hot": bool(sources),
            "match_level": level,
            "match_sources": sources,
            "industry": industry,
        }

    index_slot = (market.get("index") or {}).get("latest_slot") or flow_meta.get("latest_slot") or "midday"
    constraints: list[str] = [
        "午间不采财联社 B 层长文，仅 A 层看盘可用。",
        f"指数/资金流为上午盘 slot={index_slot}，勿按全日收盘解读。",
        "服务目标为下午午盘（13:00 起），禁止以「明日开盘」「次日」为主轴。",
    ]
    if not main_available:
        constraints.append("大盘主力不可用，禁止写「两市主力净流入/流出」。")
    if not trust.get("sector_flow"):
        constraints.append("行业资金 TOP 不可用，禁止写行业资金流向排名。")
    if not flow_ref:
        constraints.append("flow_reference 不可用，禁止引用 flow_score 作环境判断。")
    if trust.get("northbound_suspicious"):
        constraints.append("北向为零且存疑，勿作强多空依据。")

    l1_parts = [
        f"池子参考{sentiment.get('pool_signal', '—')}（{sentiment.get('limit_up_count', '—')}涨停）",
        f"热度{cls_fin.get('market_heat', '—')}°",
        f"沪指{sh.get('pct_chg', '—')}%",
        f"创业板{cy.get('pct_chg', '—')}%",
    ]
    if index_note:
        l1_parts.append(index_note)
    if not main_available:
        l1_parts.append("大盘主力不可用")
    if trust.get("northbound_suspicious"):
        l1_parts.append("北向存疑")
    if trust.get("watchlist_flow"):
        l1_parts.append(f"自选主力净{'流入' if total_net >= 0 else '流出'}{abs(total_net):.1f}亿")

    l2_parts = []
    if wind_plates:
        l2_parts.append("风口：" + "、".join(w["name"] for w in wind_plates[:3] if w.get("name")))
    if mainlines:
        l2_parts.append("主线：" + "、".join(m["name"] for m in mainlines[:2] if m.get("name")))
    if hot_industries:
        l2_parts.append(
            "池热点："
            + "、".join(f"{h['name']}({h.get('limit_up_count', '')})" for h in hot_industries[:3] if h.get("name"))
        )

    l1_brief = "上午盘：" + "；".join(l1_parts)[:96]
    l2_brief = "上午盘：" + "；".join(l2_parts)[:76] if l2_parts else "上午盘：—"

    return {
        "l1": {
            "axes": {
                "pool": {
                    "signal": sentiment.get("pool_signal"),
                    "score": sentiment.get("pool_score"),
                    "limit_up": sentiment.get("limit_up_count"),
                    "broken_limit": sentiment.get("broken_limit_count"),
                },
                "breadth": {
                    "market_heat": cls_fin.get("market_heat"),
                    "turnover": cls_fin.get("turnover"),
                    "rise_count": cls_fin.get("rise_count"),
                    "fall_count": cls_fin.get("fall_count"),
                },
                "index": {"sh": sh, "cy": cy, "note": index_note},
                "capital": {
                    "northbound_net_yi": north.get("net_yi"),
                    "northbound_suspicious": trust.get("northbound_suspicious"),
                    "market_main_net_yi": mkt.get("main_net_yi"),
                    "market_main_available": main_available,
                    "flow_reference_available": flow_ref,
                    "watchlist": wl_summary,
                },
            },
            "crosscheck": crosscheck,
        },
        "l2": {
            "mainlines": mainlines,
            "wind_plates": wind_plates,
            "hot_industries": hot_industries,
            "leaders": sentiment.get("leaders") or [],
        },
        "watchlist_flow_summary": wl_summary,
        "industry_in_hot_by_code": industry_in_hot,
        "constraints": constraints,
        "l1_brief": l1_brief,
        "l2_brief": l2_brief,
    }


__all__ = ["build_market_local"]
