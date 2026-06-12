"""盘中采集：默认全自选，同股只保留一条。"""
from __future__ import annotations

from datetime import date

from core.config import intraday_cfg, normalize_code
from morning.codes import codes_from_quote
from watchlist.loader import dedupe_stocks_by_code, load_stocks, watchlist_by_code
from watchlist.ths_blocks import StockItem, ThsBlocksError


def _stocks_from_codes(codes: list[str]) -> list[StockItem]:
    wl_map = watchlist_by_code()
    items: list[StockItem] = []
    seen: set[str] = set()
    for raw in codes:
        code = normalize_code(str(raw).strip())
        if not code or code in seen:
            continue
        seen.add(code)
        item = wl_map.get(code)
        if item is not None:
            items.append(item)
        else:
            items.append(StockItem(code=code, name=code, group="", block_id=""))
    return dedupe_stocks_by_code(items)


def _default_watchlist_stocks(*, on_date: date | None = None) -> list[StockItem]:
    try:
        stocks = dedupe_stocks_by_code(load_stocks())
        if stocks:
            return stocks
    except ThsBlocksError:
        pass

    cal = on_date or date.today()
    from_quote, _ = codes_from_quote(cal)
    if from_quote:
        return _stocks_from_codes(from_quote)

    raw = intraday_cfg().get("codes") or []
    if raw:
        return _stocks_from_codes([str(c) for c in raw])
    return []


def resolve_intraday_stocks(
    cli_codes: list[str] | None = None,
    *,
    on_date: date | None = None,
) -> list[StockItem]:
    """CLI --codes 优先；默认 analyze_blocks 全自选并按 code 去重。"""
    if cli_codes:
        return _stocks_from_codes(cli_codes)
    return _default_watchlist_stocks(on_date=on_date)


def resolve_intraday_codes(
    cli_codes: list[str] | None = None,
    *,
    on_date: date | None = None,
) -> list[str]:
    return [s.code for s in resolve_intraday_stocks(cli_codes, on_date=on_date)]
