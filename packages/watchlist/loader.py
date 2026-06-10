from __future__ import annotations

from core.config import auction_cfg, legacy_config_path, load_config, normalize_code, ths_cfg
from watchlist.ths_blocks import StockItem, ThsBlocksError, load_stocks_from_ths


def watchlist_group_names() -> list[str]:
    ab = ths_cfg().get("analyze_blocks") or {}
    names = ab.get("by_name") or []
    return [str(n).strip() for n in names if str(n).strip()]


def load_stocks() -> list[StockItem]:
    """全 analyze_blocks 白名单自选（对照老项目 watchlist.load_stocks）。"""
    return load_stocks_from_ths()


def watchlist_by_code_from(stocks: list[StockItem]) -> dict[str, StockItem]:
    """给定自选行列表，按 code 去重（多板块取 tier_groups 更靠前）。"""
    return {normalize_code(s.code): s for s in dedupe_stocks_by_code(stocks)}


def watchlist_by_code() -> dict[str, StockItem]:
    """自选按 code 去重；多板块重复时取 tier_groups 更靠前的板块。"""
    return watchlist_by_code_from(load_stocks())


def tier_group_names() -> list[str]:
    groups = auction_cfg().get("tier_groups")
    if isinstance(groups, list) and groups:
        return [str(g).strip() for g in groups if str(g).strip()]
    return ["我的", "想买的"]


def dedupe_stocks_by_code(stocks: list[StockItem]) -> list[StockItem]:
    """同股只保留一条；多板块重复时取 tier_groups 里更靠前的板块。"""
    rank = {g: i for i, g in enumerate(tier_group_names())}
    best: dict[str, StockItem] = {}
    for s in stocks:
        code = normalize_code(s.code)
        if not code:
            continue
        prev = best.get(code)
        if prev is None or rank.get(s.group, 999) < rank.get(prev.group, 999):
            best[code] = s
    seen: set[str] = set()
    out: list[StockItem] = []
    for s in stocks:
        code = normalize_code(s.code)
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(best[code])
    return out


def load_tier_stocks(*, codes: list[str] | None = None) -> list[StockItem]:
    if codes:
        items = [StockItem(code=normalize_code(c), name=normalize_code(c), group="CLI") for c in codes]
        return dedupe_stocks_by_code(items)
    cfg = load_config()
    legacy = legacy_config_path()
    if legacy and not (cfg.get("ths") or {}).get("account_dir"):
        import yaml

        with legacy.open(encoding="utf-8") as f:
            ext = yaml.safe_load(f) or {}
        if ext.get("ths"):
            cfg = {**cfg, "ths": ext["ths"]}
    try:
        stocks = load_stocks_from_ths()
    except ThsBlocksError:
        if not (cfg.get("ths") or {}).get("account_dir"):
            raise SystemExit("请配置 config.yaml 的 ths.account_dir，或使用 --codes")
        raise
    allow = set(tier_group_names())
    filtered = [s for s in stocks if s.group in allow]
    if not filtered:
        raise SystemExit(f"白名单板块 {sorted(allow)} 下无股票")
    return dedupe_stocks_by_code(filtered)
