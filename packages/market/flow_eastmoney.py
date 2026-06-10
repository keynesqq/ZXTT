"""东财资金流 HTTP 直连：共享 httpx 会话、节流、ulist 批量。"""
from __future__ import annotations

import math
import random
import time
from threading import Lock
from typing import Any

import httpx
import pandas as pd

from core.config import flow_cfg, feeds_cfg, normalize_code

_EM_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_DATACENTER = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_PUSH2 = "https://push2.eastmoney.com/api/qt/clist/get"
_PUSH2HIS = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
_ULIST_NP = "https://push2.eastmoney.com/api/qt/ulist.np/get"
_UT = "b2884a393a59ad64002292a3e90d46a5"
_RETRY = 3

_HSGT_HIST_SYMBOL = {
    "北向资金": "5",
    "沪股通": "1",
    "深股通": "3",
}

_client: httpx.Client | None = None
_throttle_lock = Lock()
_last_throttle_at = 0.0


def _timeout_sec() -> float:
    try:
        return max(5.0, float(feeds_cfg().get("akshare_timeout_sec") or 45))
    except (TypeError, ValueError):
        return 45.0


def _request_interval_sec() -> float:
    try:
        return max(0.5, float(flow_cfg().get("request_interval_sec", 1.0)))
    except (TypeError, ValueError):
        return 1.0


def _headers(*, referer: str = "https://data.eastmoney.com/") -> dict[str, str]:
    return {"User-Agent": _EM_UA, "Referer": referer}


def open_flow_session() -> None:
    global _client, _last_throttle_at
    close_flow_session()
    _client = httpx.Client(timeout=_timeout_sec(), http2=False)
    _last_throttle_at = 0.0


def close_flow_session() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def _client_or_raise() -> httpx.Client:
    if _client is None:
        open_flow_session()
    assert _client is not None
    return _client


def _throttle() -> None:
    global _last_throttle_at
    with _throttle_lock:
        interval = _request_interval_sec()
        elapsed = time.monotonic() - _last_throttle_at
        if elapsed < interval:
            time.sleep(interval - elapsed + random.uniform(0.05, 0.25))
        _last_throttle_at = time.monotonic()


def _get_json(
    url: str,
    params: dict[str, Any],
    *,
    referer: str = "https://data.eastmoney.com/",
) -> dict[str, Any]:
    last_err: Exception | None = None
    client = _client_or_raise()
    for attempt in range(_RETRY):
        try:
            _throttle()
            resp = client.get(url, params=params, headers=_headers(referer=referer))
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as e:
            last_err = e
            if attempt + 1 < _RETRY:
                time.sleep((2**attempt) + random.uniform(0.1, 0.5))
    assert last_err is not None
    raise last_err


def code_to_em_secid(code: str) -> str:
    c = normalize_code(code)
    if c.startswith(("5", "6", "9")):
        return f"1.{c}"
    return f"0.{c}"


def _chunked(items: list[str], size: int) -> list[list[str]]:
    if size <= 0:
        return [items]
    return [items[i : i + size] for i in range(0, len(items), size)]


def fetch_hsgt_summary_df() -> pd.DataFrame | None:
    params = {
        "reportName": "RPT_MUTUAL_QUOTA",
        "columns": "TRADE_DATE,MUTUAL_TYPE,BOARD_TYPE,MUTUAL_TYPE_NAME,FUNDS_DIRECTION,"
        "INDEX_CODE,INDEX_NAME,BOARD_CODE",
        "quoteColumns": "status~07~BOARD_CODE,dayNetAmtIn~07~BOARD_CODE,dayAmtRemain~07~BOARD_CODE,"
        "dayAmtThreshold~07~BOARD_CODE,f104~07~BOARD_CODE,f105~07~BOARD_CODE,"
        "f106~07~BOARD_CODE,f3~03~INDEX_CODE~INDEX_f3,netBuyAmt~07~BOARD_CODE",
        "quoteType": "0",
        "pageNumber": "1",
        "pageSize": "2000",
        "sortTypes": "1",
        "sortColumns": "MUTUAL_TYPE",
        "source": "WEB",
        "client": "WEB",
    }
    data_json = _get_json(_DATACENTER, params, referer="https://data.eastmoney.com/hsgt/")
    rows = (data_json.get("result") or {}).get("data")
    if not rows:
        return None
    temp_df = pd.DataFrame(rows)
    temp_df.columns = [
        "交易日",
        "-",
        "类型",
        "板块",
        "资金方向",
        "-",
        "相关指数",
        "-",
        "交易状态",
        "资金净流入",
        "当日资金余额",
        "-",
        "上涨数",
        "下跌数",
        "持平数",
        "指数涨跌幅",
        "成交净买额",
    ]
    temp_df = temp_df[
        [
            "交易日",
            "类型",
            "板块",
            "资金方向",
            "交易状态",
            "成交净买额",
            "资金净流入",
            "当日资金余额",
            "上涨数",
            "持平数",
            "下跌数",
            "相关指数",
            "指数涨跌幅",
        ]
    ]
    temp_df["交易日"] = pd.to_datetime(temp_df["交易日"], errors="coerce").dt.date
    for col in ("成交净买额", "资金净流入", "当日资金余额"):
        temp_df[col] = pd.to_numeric(temp_df[col], errors="coerce") / 10000
    for col in ("上涨数", "持平数", "下跌数", "指数涨跌幅"):
        temp_df[col] = pd.to_numeric(temp_df[col], errors="coerce")
    return temp_df


def fetch_hsgt_hist_df(symbol: str) -> pd.DataFrame | None:
    code = _HSGT_HIST_SYMBOL.get(symbol)
    if not code:
        return None
    params: dict[str, Any] = {
        "sortColumns": "TRADE_DATE",
        "sortTypes": "-1",
        "pageSize": "1000",
        "pageNumber": "1",
        "reportName": "RPT_MUTUAL_DEAL_HISTORY",
        "columns": "ALL",
        "source": "WEB",
        "client": "WEB",
        "filter": f'(MUTUAL_TYPE="00{code}")',
    }
    data_json = _get_json(_DATACENTER, params, referer="https://data.eastmoney.com/hsgt/")
    result = data_json.get("result") or {}
    pages = int(result.get("pages") or 1)
    temp_list: list[pd.DataFrame] = []
    for page in range(1, pages + 1):
        params["pageNumber"] = str(page)
        chunk = _get_json(_DATACENTER, params, referer="https://data.eastmoney.com/hsgt/")
        rows = (chunk.get("result") or {}).get("data") or []
        if rows:
            temp_list.append(pd.DataFrame(rows))
    if not temp_list:
        return None
    big_df = pd.concat(temp_list, ignore_index=True)
    big_df = big_df.rename(
        columns={
            "TRADE_DATE": "日期",
            "FUND_INFLOW": "当日资金流入",
            "NET_DEAL_AMT": "当日成交净买额",
        }
    )
    big_df = big_df[["日期", "当日成交净买额", "当日资金流入"]]
    big_df["日期"] = pd.to_datetime(big_df["日期"], errors="coerce").dt.date
    big_df["当日资金流入"] = pd.to_numeric(big_df["当日资金流入"], errors="coerce") / 100
    big_df["当日成交净买额"] = pd.to_numeric(big_df["当日成交净买额"], errors="coerce") / 100
    return big_df


def _ulist_diff(secids: str, *, fields: str, referer: str) -> list[dict[str, Any]]:
    params = {
        "fltt": "2",
        "secids": secids,
        "fields": fields,
        "ut": _UT,
        "_": int(time.time() * 1000),
    }
    data_json = _get_json(_ULIST_NP, params, referer=referer)
    return list((data_json.get("data") or {}).get("diff") or [])


def fetch_market_flow_df() -> pd.DataFrame | None:
    params = {
        "lmt": "0",
        "klt": "101",
        "secid": "1.000001",
        "secid2": "0.399001",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "ut": _UT,
        "_": int(time.time() * 1000),
    }
    data_json = _get_json(_PUSH2HIS, params, referer="https://data.eastmoney.com/zjlx/dpzjlx.html")
    klines = ((data_json.get("data") or {}).get("klines")) or []
    if not klines:
        return None
    temp_df = pd.DataFrame([item.split(",") for item in klines])
    temp_df.columns = [
        "日期",
        "主力净流入-净额",
        "小单净流入-净额",
        "中单净流入-净额",
        "大单净流入-净额",
        "超大单净流入-净额",
        "主力净流入-净占比",
        "小单净流入-净占比",
        "中单净流入-净占比",
        "大单净流入-净占比",
        "超大单净流入-净占比",
        "上证-收盘价",
        "上证-涨跌幅",
        "深证-收盘价",
        "深证-涨跌幅",
    ]
    temp_df = temp_df[
        [
            "日期",
            "上证-收盘价",
            "上证-涨跌幅",
            "深证-收盘价",
            "深证-涨跌幅",
            "主力净流入-净额",
            "主力净流入-净占比",
            "超大单净流入-净额",
            "超大单净流入-净占比",
            "大单净流入-净额",
            "大单净流入-净占比",
            "中单净流入-净额",
            "中单净流入-净占比",
            "小单净流入-净额",
            "小单净流入-净占比",
        ]
    ]
    temp_df["日期"] = pd.to_datetime(temp_df["日期"], errors="coerce").dt.date
    for col in temp_df.columns:
        if col == "日期":
            continue
        temp_df[col] = pd.to_numeric(temp_df[col], errors="coerce")
    return temp_df


def fetch_stocks_flow_batch(codes: list[str]) -> pd.DataFrame | None:
    """自选批量主力（ulist.np，每批 stock_batch_size 只，通常 1 次）。"""
    normalized = [normalize_code(c) for c in codes if normalize_code(c)]
    if not normalized:
        return None
    batch_size = int(flow_cfg().get("stock_batch_size", 50))
    fields = "f12,f14,f2,f3,f62,f184"
    parsed: list[dict[str, Any]] = []
    for chunk in _chunked(normalized, batch_size):
        secids = ",".join(code_to_em_secid(c) for c in chunk)
        rows = _ulist_diff(
            secids,
            fields=fields,
            referer="https://data.eastmoney.com/zjlx/detail.html",
        )
        for row in rows:
            code = normalize_code(str(row.get("f12") or ""))
            if not code:
                continue
            parsed.append(
                {
                    "代码": code,
                    "名称": str(row.get("f14") or "").strip(),
                    "今日涨跌幅": pd.to_numeric(row.get("f3"), errors="coerce"),
                    "今日主力净流入-净额": pd.to_numeric(row.get("f62"), errors="coerce"),
                }
            )
    if not parsed:
        return None
    return pd.DataFrame(parsed)


def _fetch_clist_pages(
    *,
    fs: str,
    fid: str,
    stat: str,
    fields: str,
    max_pages: int,
    referer: str,
    fid_key: str = "fid",
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "pn": "1",
        "pz": "100",
        "po": "1",
        "np": "1",
        "ut": _UT,
        "fltt": "2",
        "invt": "2",
        fid_key: fid,
        "fs": fs,
        "fields": fields,
        "rt": "52975239",
        "_": int(time.time() * 1000),
    }
    if stat:
        params["stat"] = stat
    first = _get_json(_PUSH2, params, referer=referer)
    data = first.get("data") or {}
    total = int(data.get("total") or 0)
    total_page = min(max_pages, max(1, math.ceil(total / 100)))
    rows: list[dict[str, Any]] = list(data.get("diff") or [])
    for page in range(2, total_page + 1):
        params["pn"] = str(page)
        chunk = _get_json(_PUSH2, params, referer=referer)
        rows.extend((chunk.get("data") or {}).get("diff") or [])
    return rows


def fetch_sector_rank_df(*, max_pages: int = 3) -> pd.DataFrame | None:
    rows = _fetch_clist_pages(
        fs="m:90 t:2",
        fid="f62",
        stat="1",
        fields="f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124",
        max_pages=max_pages,
        referer="https://data.eastmoney.com/bkzj/hy.html",
        fid_key="fid0",
    )
    if not rows:
        return None
    temp_df = pd.DataFrame(rows)
    temp_df.rename(
        columns={
            "f14": "名称",
            "f3": "今日涨跌幅",
            "f62": "今日主力净流入-净额",
        },
        inplace=True,
    )
    temp_df = temp_df[["名称", "今日涨跌幅", "今日主力净流入-净额"]]
    temp_df["今日涨跌幅"] = pd.to_numeric(temp_df["今日涨跌幅"], errors="coerce")
    temp_df["今日主力净流入-净额"] = pd.to_numeric(temp_df["今日主力净流入-净额"], errors="coerce")
    temp_df.sort_values(["今日主力净流入-净额"], ascending=False, inplace=True, ignore_index=True)
    return temp_df


def fetch_stock_rank_df(
    *,
    stop_codes: set[str] | None = None,
    max_pages: int = 80,
) -> pd.DataFrame | None:
    """全市场排行兜底（分页，易触发限流，仅作 fallback）。"""
    fields = "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124"
    fs = "m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2"
    params: dict[str, Any] = {
        "fid": "f62",
        "po": "1",
        "pz": "100",
        "pn": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "ut": _UT,
        "fs": fs,
        "fields": fields,
    }
    first = _get_json(_PUSH2, params, referer="https://data.eastmoney.com/zjlx/detail.html")
    data = first.get("data") or {}
    total = int(data.get("total") or 0)
    total_page = min(max_pages, max(1, math.ceil(total / 100)))
    found: set[str] = set()
    parsed: list[dict[str, Any]] = []

    def _consume(diff: list[dict[str, Any]]) -> None:
        for row in diff:
            code = normalize_code(str(row.get("f12") or ""))
            if not code:
                continue
            parsed.append(
                {
                    "代码": code,
                    "名称": str(row.get("f14") or "").strip(),
                    "今日涨跌幅": pd.to_numeric(row.get("f3"), errors="coerce"),
                    "今日主力净流入-净额": pd.to_numeric(row.get("f62"), errors="coerce"),
                }
            )
            if stop_codes and code in stop_codes:
                found.add(code)

    _consume(list(data.get("diff") or []))
    for page in range(2, total_page + 1):
        if stop_codes and found >= stop_codes:
            break
        params["pn"] = str(page)
        chunk = _get_json(_PUSH2, params, referer="https://data.eastmoney.com/zjlx/detail.html")
        _consume(list((chunk.get("data") or {}).get("diff") or []))

    if not parsed:
        return None
    return pd.DataFrame(parsed)
