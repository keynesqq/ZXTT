"""东财资金流拉取与字段归一（直连优先，AkShare 兜底）。"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

import pandas as pd

from core.config import flow_cfg, normalize_code
from feeds.eastmoney import call_akshare
from watchlist.loader import dedupe_stocks_by_code, load_stocks
from watchlist.ths_blocks import StockItem


def yuan_to_yi(raw: Any) -> float | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        return round(float(raw) / 1e8, 4)
    except (TypeError, ValueError):
        return None


def _yi_from_hsgt(raw: Any) -> float | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        return round(float(raw), 4)
    except (TypeError, ValueError):
        return None


def _row_for_date(df: pd.DataFrame | None, col: str, target: date) -> pd.Series | None:
    if df is None or df.empty or col not in df.columns:
        return None
    for _, row in df.iterrows():
        val = row.get(col)
        if val == target or str(val) == target.isoformat():
            return row
    return None


def _parse_connect_status(raw: Any) -> str:
    s = str(raw or "").strip()
    if s in ("1", "开放", "open"):
        return "open"
    if s in ("0", "关闭", "closed"):
        return "closed"
    return s or "unknown"


def _use_direct() -> bool:
    primary = str(flow_cfg().get("primary", "eastmoney_direct")).strip().lower()
    return primary in ("eastmoney_direct", "direct", "httpx")


def _use_akshare_fallback() -> bool:
    fb = flow_cfg().get("fallback", "eastmoney_akshare")
    if fb is False:
        return False
    return str(fb or "").strip().lower() not in ("false", "none", "off", "0", "")


def _load_df(
    label: str,
    direct_fn: Callable[[], pd.DataFrame | None],
    akshare_fn: Callable[[], pd.DataFrame | None],
) -> tuple[pd.DataFrame | None, list[str]]:
    warnings: list[str] = []
    if _use_direct():
        try:
            df = direct_fn()
            if df is not None and not df.empty:
                return df, warnings
        except Exception as e:
            warnings.append(f"{label}: 直连失败 ({e})")
    if _use_akshare_fallback():
        try:
            df = akshare_fn()
            if df is not None and not df.empty:
                if warnings:
                    warnings.append(f"{label}: 已改用 AkShare 兜底")
                return df, warnings
        except Exception as e:
            warnings.append(f"{label}: AkShare 失败 ({e})")
            return None, warnings
        warnings.append(f"{label}: AkShare 无返回")
        return None, warnings
    if not warnings:
        warnings.append(f"{label}: 直连无返回")
    return None, warnings


def _parse_northbound_from_summary(df: pd.DataFrame, trade_date: date) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    north: dict[str, Any] = {
        "net_yi": None,
        "sh_connect_net_yi": None,
        "sz_connect_net_yi": None,
        "connect_status": {},
        "data_as_of": trade_date.isoformat(),
        "extra": {},
    }
    _SH_KINDS = frozenset({"沪股通", "沪港通"})
    _SZ_KINDS = frozenset({"深股通", "深港通"})

    day_rows = df[df["交易日"] == trade_date] if "交易日" in df.columns else df
    if day_rows.empty:
        day_rows = df
    sh_net: float | None = None
    sz_net: float | None = None
    net_inflow_sh: float | None = None
    net_inflow_sz: float | None = None
    for _, row in day_rows.iterrows():
        direction = str(row.get("资金方向") or "").strip()
        kind = str(row.get("类型") or "").strip()
        if direction != "北向":
            continue
        deal = _yi_from_hsgt(row.get("成交净买额"))
        inflow = _yi_from_hsgt(row.get("资金净流入"))
        status = _parse_connect_status(row.get("交易状态"))
        if kind in _SH_KINDS:
            sh_net = deal if deal is not None else sh_net
            net_inflow_sh = inflow
            north["connect_status"]["sh"] = status
        elif kind in _SZ_KINDS:
            sz_net = deal if deal is not None else sz_net
            net_inflow_sz = inflow
            north["connect_status"]["sz"] = status
    if sh_net is not None or sz_net is not None:
        north["net_yi"] = round((sh_net or 0) + (sz_net or 0), 4)
    north["sh_connect_net_yi"] = sh_net
    north["sz_connect_net_yi"] = sz_net
    if net_inflow_sh is not None or net_inflow_sz is not None:
        north["extra"]["net_inflow_yi"] = {
            "sh": net_inflow_sh,
            "sz": net_inflow_sz,
            "total": round((net_inflow_sh or 0) + (net_inflow_sz or 0), 4),
        }
    if north["net_yi"] is None and sh_net is None and sz_net is None:
        warnings.append("北向: 当日 summary 无沪港通/深港通北向净买额")
    return north, warnings


def _parse_northbound_from_hist(
    *,
    trade_date: date,
    total_df: pd.DataFrame | None,
    sh_df: pd.DataFrame | None,
    sz_df: pd.DataFrame | None,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    north: dict[str, Any] = {
        "net_yi": None,
        "sh_connect_net_yi": None,
        "sz_connect_net_yi": None,
        "connect_status": {},
        "data_as_of": trade_date.isoformat(),
        "extra": {},
    }
    total_row = _row_for_date(total_df, "日期", trade_date)
    sh_row = _row_for_date(sh_df, "日期", trade_date)
    sz_row = _row_for_date(sz_df, "日期", trade_date)
    if total_row is not None:
        north["net_yi"] = _yi_from_hsgt(total_row.get("当日成交净买额"))
        north["extra"]["net_inflow_yi"] = {"total": _yi_from_hsgt(total_row.get("当日资金流入"))}
    if sh_row is not None:
        north["sh_connect_net_yi"] = _yi_from_hsgt(sh_row.get("当日成交净买额"))
    if sz_row is not None:
        north["sz_connect_net_yi"] = _yi_from_hsgt(sz_row.get("当日成交净买额"))
    if north["net_yi"] is None and north["sh_connect_net_yi"] is not None and north["sz_connect_net_yi"] is not None:
        north["net_yi"] = round(north["sh_connect_net_yi"] + north["sz_connect_net_yi"], 4)
    if north["net_yi"] is None:
        warnings.append(f"北向: 历史 {trade_date.isoformat()} 无成交净买额")
    return north, warnings


def fetch_northbound(*, trade_date: date, live_day: bool) -> tuple[dict[str, Any], list[str]]:
    from market import flow_eastmoney

    import akshare as ak

    if live_day:

        def _direct() -> pd.DataFrame | None:
            return flow_eastmoney.fetch_hsgt_summary_df()

        def _ak() -> pd.DataFrame | None:
            return call_akshare(ak.stock_hsgt_fund_flow_summary_em)

        df, w = _load_df("北向", _direct, _ak)
        if df is None:
            north = {
                "net_yi": None,
                "sh_connect_net_yi": None,
                "sz_connect_net_yi": None,
                "connect_status": {},
                "data_as_of": trade_date.isoformat(),
                "extra": {},
            }
            return north, w
        parsed, pw = _parse_northbound_from_summary(df, trade_date)
        return parsed, w + pw

    def _hist_direct(symbol: str) -> pd.DataFrame | None:
        return flow_eastmoney.fetch_hsgt_hist_df(symbol)

    def _hist_ak(symbol: str) -> pd.DataFrame | None:
        return call_akshare(ak.stock_hsgt_hist_em, symbol=symbol)

    warnings: list[str] = []
    total_df, w1 = _load_df("北向", lambda: _hist_direct("北向资金"), lambda: _hist_ak("北向资金"))
    sh_df, w2 = _load_df("北向沪", lambda: _hist_direct("沪股通"), lambda: _hist_ak("沪股通"))
    sz_df, w3 = _load_df("北向深", lambda: _hist_direct("深股通"), lambda: _hist_ak("深股通"))
    warnings.extend(w1 + w2 + w3)
    north, pw = _parse_northbound_from_hist(
        trade_date=trade_date,
        total_df=total_df,
        sh_df=sh_df,
        sz_df=sz_df,
    )
    return north, warnings + pw


def _parse_market_row(row: pd.Series, *, trade_date: date, source_channel: str) -> dict[str, Any]:
    return {
        "main_net_yi": yuan_to_yi(row.get("主力净流入-净额")),
        "super_large_net_yi": yuan_to_yi(row.get("超大单净流入-净额")),
        "large_net_yi": yuan_to_yi(row.get("大单净流入-净额")),
        "medium_net_yi": yuan_to_yi(row.get("中单净流入-净额")),
        "small_net_yi": yuan_to_yi(row.get("小单净流入-净额")),
        "main_net_pct": _yi_from_hsgt(row.get("主力净流入-净占比")),
        "data_as_of": trade_date.isoformat(),
        "sh_index_pct_chg": _yi_from_hsgt(row.get("上证-涨跌幅")),
        "sz_index_pct_chg": _yi_from_hsgt(row.get("深证-涨跌幅")),
        "source_channel": source_channel,
    }


def fetch_market_flow(*, trade_date: date, live_day: bool = False) -> tuple[dict[str, Any], list[str]]:
    from market import flow_eastmoney

    import akshare as ak

    empty: dict[str, Any] = {
        "main_net_yi": None,
        "super_large_net_yi": None,
        "large_net_yi": None,
        "medium_net_yi": None,
        "small_net_yi": None,
        "main_net_pct": None,
        "data_as_of": trade_date.isoformat(),
    }
    warnings: list[str] = []

    if live_day and _use_direct():
        try:
            df = flow_eastmoney.fetch_market_flow_df()
            if df is not None and not df.empty:
                row = _row_for_date(df, "日期", trade_date)
                if row is not None:
                    parsed = _parse_market_row(row, trade_date=trade_date, source_channel="push2his")
                    if parsed.get("main_net_yi") is not None:
                        return parsed, warnings
                    warnings.append(f"大盘主力: {trade_date.isoformat()} 当日行无主力净流入")
                else:
                    warnings.append(f"大盘主力: push2his 无 {trade_date.isoformat()} 当日行，改用兜底")
        except Exception as e:
            warnings.append(f"大盘主力: push2his 直连失败 ({e})")

    df, load_warnings = _load_df(
        "大盘主力",
        flow_eastmoney.fetch_market_flow_df,
        lambda: call_akshare(ak.stock_market_fund_flow),
    )
    warnings.extend(load_warnings)
    if df is None:
        return empty, warnings
    row = _row_for_date(df, "日期", trade_date)
    if row is None and not df.empty:
        row = df.iloc[-1]
        warnings.append(f"大盘主力: {trade_date.isoformat()} 无行，使用最近 {row.get('日期')}")
    if row is None:
        warnings.append(f"大盘主力: {trade_date.isoformat()} 无数据行")
        return empty, warnings
    channel = "push2his" if _use_direct() else "akshare"
    return _parse_market_row(row, trade_date=trade_date, source_channel=channel), warnings


def _sector_rows(df: pd.DataFrame | None, *, top_n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    if df is None or df.empty:
        warnings.append("行业板块: 接口无返回")
        return [], [], warnings
    name_col = "名称"
    net_col = "今日主力净流入-净额"
    pct_col = "今日涨跌幅"
    if net_col not in df.columns:
        warnings.append("行业板块: 列结构异常")
        return [], [], warnings
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        name = str(row.get(name_col) or "").strip()
        if not name:
            continue
        rows.append(
            {
                "name": name,
                "main_net_yi": yuan_to_yi(row.get(net_col)),
                "pct_chg": _yi_from_hsgt(row.get(pct_col)) if pct_col in df.columns else None,
            }
        )
    rows.sort(key=lambda x: x["main_net_yi"] if x["main_net_yi"] is not None else float("-inf"), reverse=True)
    inflow = [r for r in rows if r.get("main_net_yi") is not None and r["main_net_yi"] > 0][:top_n]
    outflow = sorted(
        [r for r in rows if r.get("main_net_yi") is not None and r["main_net_yi"] < 0],
        key=lambda x: x["main_net_yi"],
    )[:top_n]
    return inflow, outflow, warnings


def fetch_sector_tops(*, top_n: int | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    from market import flow_eastmoney

    import akshare as ak

    cfg = flow_cfg()
    n = int(top_n if top_n is not None else cfg.get("sector_top_n", 10))
    max_pages = int(cfg.get("sector_max_pages", 3))

    df, warnings = _load_df(
        "行业板块",
        lambda: flow_eastmoney.fetch_sector_rank_df(max_pages=max_pages),
        lambda: call_akshare(ak.stock_sector_fund_flow_rank, indicator="今日", sector_type="行业资金流"),
    )
    inflow, outflow, row_warnings = _sector_rows(df, top_n=n)
    return inflow, outflow, warnings + row_warnings


def fetch_watchlist_flow(
    stocks: list[StockItem] | None = None,
    *,
    missing_warn: bool | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    from market import flow_eastmoney

    import akshare as ak

    cfg = flow_cfg()
    warn_missing = bool(cfg.get("watchlist_missing_warn", True) if missing_warn is None else missing_warn)
    deduped = dedupe_stocks_by_code(stocks if stocks is not None else load_stocks())
    if not deduped:
        return [], ["自选: 无股票列表"]

    need_codes = {normalize_code(s.code) for s in deduped}
    code_list = [normalize_code(s.code) for s in deduped]
    max_pages = int(cfg.get("stock_rank_max_pages", 80))
    warnings: list[str] = []
    df: pd.DataFrame | None = None

    if _use_direct():
        try:
            df = flow_eastmoney.fetch_stocks_flow_batch(code_list)
        except Exception as e:
            warnings.append(f"自选: 批量直连失败 ({e})")
        if df is None or df.empty:
            try:
                df = flow_eastmoney.fetch_stock_rank_df(stop_codes=need_codes, max_pages=max_pages)
                if df is not None and not df.empty:
                    warnings.append("自选: 批量失败，已用全市场排行兜底")
            except Exception as e:
                warnings.append(f"自选: 排行直连失败 ({e})")

    if (df is None or df.empty) and _use_akshare_fallback():
        try:
            df = call_akshare(ak.stock_individual_fund_flow_rank, indicator="今日")
            if df is not None and not df.empty and warnings:
                warnings.append("自选: 已改用 AkShare 兜底")
        except Exception as e:
            warnings.append(f"自选: AkShare 失败 ({e})")

    rank_by_code: dict[str, dict[str, Any]] = {}
    if df is not None and not df.empty and "代码" in df.columns:
        net_col = "今日主力净流入-净额"
        pct_col = "今日涨跌幅"
        for _, row in df.iterrows():
            code = normalize_code(str(row.get("代码") or ""))
            if not code:
                continue
            rank_by_code[code] = {
                "main_net_yi": yuan_to_yi(row.get(net_col)),
                "pct_chg": _yi_from_hsgt(row.get(pct_col)) if pct_col in df.columns else None,
                "rank_name": str(row.get("名称") or "").strip(),
            }
    elif not warnings:
        warnings.append("自选: 接口无返回")

    out: list[dict[str, Any]] = []
    missing = 0
    for stock in deduped:
        code = normalize_code(stock.code)
        hit = rank_by_code.get(code)
        main_net = hit.get("main_net_yi") if hit else None
        if main_net is None:
            missing += 1
        out.append(
            {
                "code": code,
                "name": stock.name or (hit or {}).get("rank_name") or code,
                "group": stock.group,
                "main_net_yi": main_net,
                "pct_chg": (hit or {}).get("pct_chg"),
            }
        )
    if warn_missing and missing:
        warnings.append(f"自选: {missing} 只无主力净流入数据")
    return out, warnings


def resolve_watchlist_enabled(*, cli_watchlist: bool | None = None) -> bool:
    if cli_watchlist is True:
        return True
    if cli_watchlist is False:
        return False
    return bool(flow_cfg().get("watchlist_enabled", True))
