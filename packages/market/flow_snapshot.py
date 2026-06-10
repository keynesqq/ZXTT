"""大盘资金流快照：北向 + 大盘主力 + 行业 TOP + 自选（独立落盘）。"""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from collect.manifest import record_source, track_source
from core.config import flow_cfg
from core.io import atomic_write_text
from core.paths import ROOT
from core.trading_calendar import market_data_date, today_cn
from market.flow_sources import (
    fetch_market_flow,
    fetch_northbound,
    fetch_sector_tops,
    fetch_watchlist_flow,
    resolve_watchlist_enabled,
)
from market import flow_eastmoney

_STORAGE = ROOT / "data" / "market_flow"
_VALID_SLOTS = frozenset({"open", "morning", "midday", "evening", "manual"})
_STRONG_YI = 30.0
_WEAK_YI = -30.0


def _now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")


def load_market_flow(for_date: date | None = None) -> dict[str, Any] | None:
    d = for_date or date.today()
    path = _STORAGE / f"{d.isoformat()}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _band(net_yi: float | None) -> str:
    if net_yi is None:
        return "unknown"
    if net_yi >= _STRONG_YI:
        return "strong"
    if net_yi <= _WEAK_YI:
        return "weak"
    return "mid"


def score_flow(northbound: dict[str, Any], market: dict[str, Any]) -> tuple[int, str, str]:
    north_band = _band(northbound.get("net_yi"))
    market_band = _band(market.get("main_net_yi"))
    if north_band == "strong" and market_band == "strong":
        signal = "强"
        score = 78
    elif north_band == "weak" and market_band == "weak":
        signal = "弱"
        score = 32
    else:
        signal = "中"
        score = 55

    north_val = northbound.get("net_yi")
    market_val = market.get("main_net_yi")
    north_txt = f"北向{'净流入' if (north_val or 0) >= 0 else '净流出'}{abs(north_val or 0):.1f}亿" if north_val is not None else "北向无数据"
    market_txt = (
        f"主力{'净流入' if (market_val or 0) >= 0 else '净流出'}{abs(market_val or 0):.1f}亿"
        if market_val is not None
        else "主力无数据"
    )
    hint = f"{north_txt}；{market_txt}；参考{signal}"
    return score, signal, hint


def _snapshot_body(
    *,
    northbound: dict[str, Any],
    market: dict[str, Any],
    sectors_inflow_top: list[dict[str, Any]],
    sectors_outflow_top: list[dict[str, Any]],
    watchlist_flow: list[dict[str, Any]],
    watchlist_enabled: bool,
    warnings: list[str],
) -> dict[str, Any]:
    score, signal, hint = score_flow(northbound, market)
    collected_at = time.time()
    return {
        "collected_at": collected_at,
        "collected_at_iso": _now_iso(),
        "watchlist_enabled": watchlist_enabled,
        "northbound": northbound,
        "market": market,
        "sectors_inflow_top": sectors_inflow_top,
        "sectors_outflow_top": sectors_outflow_top,
        "watchlist_flow": watchlist_flow,
        "flow_score": score,
        "flow_signal": signal,
        "flow_hint": hint,
        "warnings": list(warnings),
    }


def _merge_snapshot(
    existing: dict[str, Any] | None,
    *,
    trade_date: date,
    calendar_date: date,
    slot: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    snap = {"slot": slot, **body}
    base: dict[str, Any] = dict(existing or {})
    base.update(
        {
            "schema_version": 1,
            "source": "akshare.eastmoney",
            "trade_date": trade_date.isoformat(),
            "calendar_date": calendar_date.isoformat(),
            "updated_at": body["collected_at"],
            "updated_at_iso": body["collected_at_iso"],
        }
    )
    merged_warnings = list(body.get("warnings") or [])
    if merged_warnings:
        base["warnings"] = merged_warnings
    elif body.get("northbound", {}).get("net_yi") is not None or body.get("market", {}).get("main_net_yi") is not None:
        base.pop("warnings", None)

    snapshots = [s for s in (base.get("snapshots") or []) if s.get("slot") != slot]
    snapshots.append(snap)
    slot_order = {"open": 0, "morning": 1, "midday": 2, "evening": 3, "manual": 4}
    snapshots.sort(key=lambda s: slot_order.get(str(s.get("slot") or ""), 99))
    base["snapshots"] = snapshots
    base["latest_slot"] = slot
    for key in (
        "watchlist_enabled",
        "northbound",
        "market",
        "sectors_inflow_top",
        "sectors_outflow_top",
        "watchlist_flow",
        "flow_score",
        "flow_signal",
        "flow_hint",
        "collected_at",
        "collected_at_iso",
    ):
        base[key] = body.get(key) if key in body else snap.get(key)
    return base


def _collect_layers(
    *,
    trade_date: date,
    calendar_date: date,
    watchlist_enabled: bool,
) -> tuple[dict[str, Any], list[str]]:
    live_day = calendar_date == today_cn()
    warnings: list[str] = []
    northbound: dict[str, Any] = {}
    market: dict[str, Any] = {}
    sectors_in: list[dict[str, Any]] = []
    sectors_out: list[dict[str, Any]] = []
    watchlist_flow: list[dict[str, Any]] = []

    flow_eastmoney.open_flow_session()
    try:
        def _north() -> tuple[dict[str, Any], list[str]]:
            with track_source(trade_date, "akshare_hsgt", calendar_date=calendar_date) as rec:
                data, w = fetch_northbound(trade_date=trade_date, live_day=live_day)
                rec["net_yi"] = data.get("net_yi")
                if data.get("net_yi") is None:
                    rec["ok"] = False
                return data, w

        def _market() -> tuple[dict[str, Any], list[str]]:
            with track_source(trade_date, "akshare_market_flow", calendar_date=calendar_date) as rec:
                data, w = fetch_market_flow(trade_date=trade_date, live_day=live_day)
                rec["main_net_yi"] = data.get("main_net_yi")
                if data.get("main_net_yi") is None:
                    rec["ok"] = False
                return data, w

        northbound, w_n = _north()
        market, w_m = _market()
        warnings.extend(w_n)
        warnings.extend(w_m)

        if live_day:
            with track_source(trade_date, "akshare_sector_flow", calendar_date=calendar_date) as rec:
                sectors_in, sectors_out, w_s = fetch_sector_tops()
                rec["inflow_count"] = len(sectors_in)
                rec["outflow_count"] = len(sectors_out)
                if not sectors_in and not sectors_out:
                    rec["ok"] = False
                warnings.extend(w_s)
        else:
            warnings.append("行业板块: 仅支持当日采集，历史日已跳过")
            record_source(
                trade_date,
                "akshare_sector_flow",
                {"ok": True, "skipped": True, "reason": "historical_date"},
                calendar_date=calendar_date,
            )

        if watchlist_enabled and live_day:
            with track_source(trade_date, "akshare_watchlist_flow", calendar_date=calendar_date) as rec:
                watchlist_flow, w_w = fetch_watchlist_flow()
                rec["count"] = len(watchlist_flow)
                rec["with_data"] = sum(1 for r in watchlist_flow if r.get("main_net_yi") is not None)
                if not watchlist_flow:
                    rec["ok"] = False
                warnings.extend(w_w)
        elif watchlist_enabled and not live_day:
            warnings.append("自选主力: 仅支持当日采集，历史日已跳过")
            record_source(
                trade_date,
                "akshare_watchlist_flow",
                {"ok": True, "skipped": True, "reason": "historical_date"},
                calendar_date=calendar_date,
            )
        else:
            record_source(
                trade_date,
                "akshare_watchlist_flow",
                {"ok": True, "skipped": True, "reason": "watchlist_disabled"},
                calendar_date=calendar_date,
            )
    finally:
        flow_eastmoney.close_flow_session()

    body = _snapshot_body(
        northbound=northbound,
        market=market,
        sectors_inflow_top=sectors_in,
        sectors_outflow_top=sectors_out,
        watchlist_flow=watchlist_flow,
        watchlist_enabled=watchlist_enabled and live_day,
        warnings=warnings,
    )
    return body, warnings


def collect_market_flow(
    *,
    calendar_date: date | None = None,
    slot: str = "evening",
    watchlist_enabled: bool | None = None,
) -> dict[str, Any]:
    cfg = flow_cfg()
    if not cfg.get("enabled", True):
        cal = calendar_date or date.today()
        trade = market_data_date(cal)
        return {
            "schema_version": 1,
            "source": "akshare.eastmoney",
            "trade_date": trade.isoformat(),
            "calendar_date": cal.isoformat(),
            "outcome": "skip",
            "message": "flow.enabled=false",
        }

    cal = calendar_date or date.today()
    trade = market_data_date(cal)
    slot_k = slot if slot in _VALID_SLOTS else "manual"
    wl = resolve_watchlist_enabled(cli_watchlist=watchlist_enabled)

    body, _ = _collect_layers(trade_date=trade, calendar_date=cal, watchlist_enabled=wl)
    payload = _merge_snapshot(
        load_market_flow(trade),
        trade_date=trade,
        calendar_date=cal,
        slot=slot_k,
        body=body,
    )
    path = _STORAGE / f"{trade.isoformat()}.json"
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    payload["path"] = str(path)
    return payload


def format_flow_prompt(data: dict[str, Any] | None) -> list[str]:
    if not data:
        return []
    north = data.get("northbound") or {}
    market = data.get("market") or {}
    if not north and not market and data.get("snapshots"):
        last = data["snapshots"][-1] or {}
        north = last.get("northbound") or {}
        market = last.get("market") or {}
    if north.get("net_yi") is None and market.get("main_net_yi") is None:
        return []

    def _fmt_yi(val: float | None) -> str:
        if val is None:
            return "—"
        return f"{val:+.2f}亿"

    lines = [
        "",
        "## [大盘资金流] 东财结构化",
        f"- 交易日: {data.get('trade_date', '—')} · 采集: {data.get('collected_at_iso', '—')}",
    ]
    slot = data.get("latest_slot")
    if slot:
        lines.append(f"- 时段: {slot}")
    lines.append(
        f"- 北向成交净买额: {_fmt_yi(north.get('net_yi'))}"
        f"（沪 {_fmt_yi(north.get('sh_connect_net_yi'))} / 深 {_fmt_yi(north.get('sz_connect_net_yi'))}）"
    )
    lines.append(f"- 大盘主力净流入: {_fmt_yi(market.get('main_net_yi'))} · 参考 {data.get('flow_signal', '—')}")
    inflow = data.get("sectors_inflow_top") or []
    if inflow:
        top = " · ".join(f"{r['name']}({_fmt_yi(r.get('main_net_yi'))})" for r in inflow[:3])
        lines.append(f"- 行业流入 TOP: {top}")
    outflow = data.get("sectors_outflow_top") or []
    if outflow:
        top = " · ".join(f"{r['name']}({_fmt_yi(r.get('main_net_yi'))})" for r in outflow[:3])
        lines.append(f"- 行业流出 TOP: {top}")
    wl = data.get("watchlist_flow") or []
    if wl:
        with_data = [r for r in wl if r.get("main_net_yi") is not None]
        if with_data:
            top = sorted(with_data, key=lambda r: r.get("main_net_yi") or 0, reverse=True)[:3]
            lines.append(
                "- 自选主力 TOP: "
                + " · ".join(f"{r.get('name')}({_fmt_yi(r.get('main_net_yi'))})" for r in top)
            )
    for w in data.get("warnings") or []:
        lines.append(f"- ⚠ {w}")
    return lines
