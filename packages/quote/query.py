"""单股/多股/全自选即时行情查询（全字段，同花顺主源 + 腾讯辅源）。"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from core.config import normalize_code
from quote.snapshot.build import build_snapshots, snapshot_row_dict
from watchlist.loader import dedupe_stocks_by_code, load_stocks, watchlist_by_code, watchlist_by_code_from
from watchlist.ths_blocks import StockItem


def resolve_query_stocks(
    codes: list[str],
    *,
    wl_map: dict[str, StockItem] | None = None,
) -> list[StockItem]:
    """按代码查：在自选里的保留分组/名称，不在自选的也可查。"""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in codes:
        code = normalize_code(str(raw).strip())
        if not code or code in seen:
            continue
        seen.add(code)
        normalized.append(code)
    if not normalized:
        return []

    resolved_map = wl_map if wl_map is not None else watchlist_by_code()
    stocks: list[StockItem] = []
    for code in normalized:
        if code in resolved_map:
            stocks.append(resolved_map[code])
        else:
            stocks.append(StockItem(code=code, name=code, group="", block_id=""))
    return stocks


def _structure_stocks_for_codes(
    fact_stocks: list[StockItem],
    watchlist_rows: list[StockItem],
) -> list[StockItem]:
    code_set = {normalize_code(s.code) for s in fact_stocks}
    from_watchlist = [s for s in watchlist_rows if normalize_code(s.code) in code_set]
    return from_watchlist if from_watchlist else fact_stocks


def query_quotes(
    codes: list[str] | None = None,
    *,
    all_watchlist: bool = False,
    save: bool = True,
    on_date: date | None = None,
) -> tuple[list[dict], Path | None, dict[str, Any]]:
    """查行情；落盘为事实 quotes + 结构 memberships。返回 (quotes, path|None, meta)。"""
    if all_watchlist:
        watchlist_rows = load_stocks()
        fact_stocks = dedupe_stocks_by_code(watchlist_rows)
        structure_stocks = watchlist_rows
        mode = "all"
    else:
        watchlist_rows = load_stocks()
        wl_map = watchlist_by_code_from(watchlist_rows)
        fact_stocks = resolve_query_stocks(codes or [], wl_map=wl_map)
        structure_stocks = _structure_stocks_for_codes(fact_stocks, watchlist_rows)
        mode = "codes"
    if not fact_stocks:
        return [], None, {"code_count": 0, "row_count": 0, "mode": mode}

    from quote.query_cache import structure_payload_from_stocks

    rows = build_snapshots(fact_stocks, fetch_industry=False, record_manifest=False)
    quotes = [snapshot_row_dict(r) for r in rows]
    memberships, structure = structure_payload_from_stocks(structure_stocks)
    meta: dict[str, Any] = {
        "mode": mode,
        "code_count": len(quotes),
        "row_count": len(memberships),
        "structure": structure,
    }
    path: Path | None = None
    if save and quotes:
        from quote.query_cache import persist_quote_query

        path = persist_quote_query(
            quotes,
            mode=mode,
            structure_stocks=structure_stocks,
            on_date=on_date,
        )
    return quotes, path, meta
