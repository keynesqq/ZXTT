"""上午盘中模拟数据：无行情接口时可跑通序列落盘。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

DEMO_DATE_ISO = "2026-06-10"


@dataclass(frozen=True)
class MockStock:
    code: str
    name: str
    group: str
    pre_close: float


MOCK_STOCKS: tuple[MockStock, ...] = (
    MockStock("600519", "贵州茅台", "我的", 1260.0),
    MockStock("000001", "平安银行", "我的", 11.0),
    MockStock("300750", "宁德时代", "想买的", 210.0),
)


def mock_stocks() -> list[MockStock]:
    return list(MOCK_STOCKS)


def _ratio(idx: int, total: int) -> float:
    if total <= 1:
        return 0.0
    return idx / (total - 1)


def build_mock_row(stock: MockStock, *, point_idx: int, point_total: int, captured_at: str) -> dict:
    r = _ratio(point_idx, point_total)
    pct = round((r - 0.5) * 2.4, 2)
    price = round(stock.pre_close * (1 + pct / 100), 3)
    open_px = round(stock.pre_close * 1.002, 3)
    high = max(price, open_px) * 1.003
    low = min(price, open_px) * 0.997
    return {
        "group": stock.group,
        "code": stock.code,
        "name": stock.name,
        "industry": "",
        "board": "主板",
        "is_st": False,
        "price": price,
        "pre_close": stock.pre_close,
        "open": open_px,
        "high": round(high, 3),
        "low": round(low, 3),
        "open_gap_pct": round((open_px / stock.pre_close - 1) * 100, 2),
        "pct_chg": pct,
        "limit_pct": 10.0,
        "limit_status": "—",
        "consecutive_boards": None,
        "amplitude": round((high - low) / stock.pre_close * 100, 2),
        "turnover": round(0.5 + r * 2.0, 2),
        "amount_yi": round(0.8 + r * 3.5, 3),
        "amount_avg_5d_yi": 1.2,
        "amount_ratio": round(0.9 + r * 0.4, 2),
        "pct_5d": round(pct * 0.6, 2),
        "pct_20d": round(pct * 1.2, 2),
        "pct_60d": None,
        "pct_ytd": None,
        "ma5": round(stock.pre_close * 1.01, 3),
        "ma20": round(stock.pre_close * 0.99, 3),
        "ma60": None,
        "ma5_dist": round((price / (stock.pre_close * 1.01) - 1) * 100, 2),
        "ma20_dist": None,
        "ma60_dist": None,
        "intraday_shape": "震荡",
        "pe": None,
        "pb": None,
        "total_mv_yi": None,
        "float_mv_yi": None,
        "snapshot_at": captured_at,
        "quote_fetched_at": captured_at,
        "warnings": [],
        "data_missing": False,
    }


def build_mock_series_points(
    schedule: list[datetime],
    *,
    stocks: list[MockStock] | None = None,
    segment: str = "morning",
) -> list[dict]:
    profiles = stocks or mock_stocks()
    total = len(schedule)
    points: list[dict] = []
    for idx, scheduled in enumerate(schedule):
        captured_at = scheduled.strftime("%Y-%m-%d %H:%M:%S")
        points.append(
            {
                "captured_at": captured_at,
                "is_final": idx == total - 1,
                "segment": segment,
                "rows": [
                    build_mock_row(s, point_idx=idx, point_total=total, captured_at=captured_at)
                    for s in profiles
                ],
            }
        )
    return points
