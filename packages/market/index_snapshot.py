"""大盘指数快照：上证/深证/创业板等（腾讯 qt，独立落盘）。"""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from collect.manifest import record_source, track_source
from core.config import index_cfg
from core.io import atomic_write_text
from core.paths import ROOT
from core.trading_calendar import market_data_date
from quote.tencent import DEFAULT_INDEX_SYMBOLS, fetch_index_snapshots

_STORAGE = ROOT / "data" / "market_index"
_VALID_SLOTS = frozenset({"open", "morning", "midday", "evening", "manual"})


def _now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")


def _resolve_symbols() -> list[tuple[str, str]]:
    cfg = index_cfg()
    raw = cfg.get("symbols")
    if not raw:
        return list(DEFAULT_INDEX_SYMBOLS)
    pairs: list[tuple[str, str]] = []
    name_map = dict(DEFAULT_INDEX_SYMBOLS)
    for item in raw:
        if isinstance(item, str):
            sym = item.strip().lower()
            if sym:
                pairs.append((sym, name_map.get(sym, sym)))
        elif isinstance(item, dict):
            sym = str(item.get("symbol") or "").strip().lower()
            if not sym:
                continue
            name = str(item.get("name") or name_map.get(sym, sym)).strip()
            pairs.append((sym, name))
    return pairs or list(DEFAULT_INDEX_SYMBOLS)


def load_market_index(for_date: date | None = None) -> dict[str, Any] | None:
    d = for_date or date.today()
    path = _STORAGE / f"{d.isoformat()}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _merge_snapshot(
    existing: dict[str, Any] | None,
    *,
    trade_date: date,
    calendar_date: date,
    slot: str,
    indices: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    collected_at = time.time()
    collected_at_iso = _now_iso()
    snap = {
        "slot": slot,
        "collected_at": collected_at,
        "collected_at_iso": collected_at_iso,
        "indices": indices,
    }
    if warnings:
        snap["warnings"] = warnings

    base: dict[str, Any] = dict(existing or {})
    base.update(
        {
            "schema_version": 2,
            "source": "tencent.qt",
            "trade_date": trade_date.isoformat(),
            "calendar_date": calendar_date.isoformat(),
            "updated_at": collected_at,
            "updated_at_iso": collected_at_iso,
        }
    )
    if warnings:
        merged_warnings = list(base.get("warnings") or [])
        for w in warnings:
            if w not in merged_warnings:
                merged_warnings.append(w)
        base["warnings"] = merged_warnings
    elif indices:
        base.pop("warnings", None)

    snapshots = [s for s in (base.get("snapshots") or []) if s.get("slot") != slot]
    snapshots.append(snap)
    slot_order = {"open": 0, "morning": 1, "midday": 2, "evening": 3, "manual": 4}
    snapshots.sort(key=lambda s: slot_order.get(str(s.get("slot") or ""), 99))
    base["snapshots"] = snapshots
    base["latest_slot"] = slot
    base["indices"] = indices
    base["collected_at"] = collected_at
    base["collected_at_iso"] = collected_at_iso
    return base


def collect_market_index(
    *,
    calendar_date: date | None = None,
    slot: str = "evening",
    symbols: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    cal = calendar_date or date.today()
    trade = market_data_date(cal)
    slot_k = slot if slot in _VALID_SLOTS else "manual"
    pairs = symbols or _resolve_symbols()
    warnings: list[str] = []

    try:
        with track_source(trade, "tencent_index", calendar_date=cal) as rec:
            indices = fetch_index_snapshots(pairs)
            rec["count"] = len(indices)
            rec["slot"] = slot_k
            if not indices:
                rec["ok"] = False
                warnings.append("指数行情: 未返回数据")
    except Exception as e:
        warnings.append(f"指数行情: {e}")
        indices = []
        record_source(
            trade,
            "tencent_index",
            {"ok": False, "error": str(e), "slot": slot_k},
            calendar_date=cal,
        )

    payload = _merge_snapshot(
        load_market_index(trade),
        trade_date=trade,
        calendar_date=cal,
        slot=slot_k,
        indices=indices,
        warnings=warnings,
    )
    path = _STORAGE / f"{trade.isoformat()}.json"
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def _fmt_pct(val: float | None) -> str:
    return f"{val:+.2f}%" if val is not None else "—"


def _fmt_num(val: float | None, digits: int = 2) -> str:
    return f"{val:.{digits}f}" if val is not None else "—"


def format_index_prompt(data: dict[str, Any] | None) -> list[str]:
    if not data:
        return []
    indices = data.get("indices") or []
    if not indices and data.get("snapshots"):
        indices = (data["snapshots"][-1] or {}).get("indices") or []
    if not indices:
        return []
    quote_times = sorted(
        {str(row.get("snapshot_at") or "").strip() for row in indices if row.get("snapshot_at")}
    )
    lines = [
        "",
        "## [指数快照] 主要指数（tencent.qt）",
        f"- 交易日: {data.get('trade_date', '—')} · 采集: {data.get('collected_at_iso', '—')}",
    ]
    slot = data.get("latest_slot")
    if slot:
        lines.append(f"- 时段: {slot}")
    if quote_times:
        lines.append(f"- 行情时刻: {quote_times[0]}" + (f"（共 {len(quote_times)} 时点）" if len(quote_times) > 1 else ""))
    for row in indices:
        name = row.get("name") or row.get("symbol") or "—"
        parts = [
            f"{name}: {_fmt_num(row.get('price'))}",
            _fmt_pct(row.get("pct_chg")),
        ]
        if row.get("change") is not None:
            parts.append(f"涨跌 {_fmt_num(row.get('change'))} 点")
        if row.get("open_gap_pct") is not None:
            parts.append(f"缺口 {_fmt_pct(row.get('open_gap_pct'))}")
        if row.get("amplitude") is not None:
            parts.append(f"振幅 {_fmt_pct(row.get('amplitude'))}")
        if row.get("amount_yi") is not None:
            parts.append(f"成交额 {_fmt_num(row.get('amount_yi'))} 亿")
        if row.get("pct_ytd") is not None:
            parts.append(f"年初至今 {_fmt_pct(row.get('pct_ytd'))}")
        lines.append("- " + " · ".join(parts))
    for w in data.get("warnings") or []:
        lines.append(f"- ⚠ {w}")
    return lines
