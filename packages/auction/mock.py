"""集合竞价模拟数据：覆盖各走势形态，无需行情接口与同花顺。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from quote.auction_snap import AuctionSnap, open_gap_pct

_CN_TZ = ZoneInfo("Asia/Shanghai")

# 演示用固定日历日（与真实交易日解耦）
DEMO_DATE_ISO = "2026-06-10"


@dataclass(frozen=True)
class MockStock:
    code: str
    name: str
    group: str
    pre_close: float
    expected_shape: str


def _idx_ratio(idx: int, total: int) -> float:
    if total <= 1:
        return 0.0
    return idx / (total - 1)


def _gap_rising(idx: int, total: int) -> float:
    return round(0.0 + 1.2 * _idx_ratio(idx, total), 2)


def _gap_falling(idx: int, total: int) -> float:
    return round(0.5 - 1.3 * _idx_ratio(idx, total), 2)


def _gap_flat(idx: int, total: int) -> float:
    _ = total
    return round(0.08 * (1 if idx % 2 == 0 else -1), 2)


def _gap_late_up(idx: int, total: int) -> float:
    if idx >= total - 1:
        return 0.55
    return 0.15


def _gap_late_down(idx: int, total: int) -> float:
    if idx >= total - 1:
        return -0.55
    return -0.15


def _gap_spike_fade(idx: int, total: int) -> float:
    r = _idx_ratio(idx, total)
    if r <= 0.5:
        return round(0.3 + 3.4 * r, 2)
    return round(2.0 - 1.4 * (r - 0.5) / 0.5, 2)


def _gap_dip_recover(idx: int, total: int) -> float:
    r = _idx_ratio(idx, total)
    if r <= 0.5:
        return round(-0.2 - 3.6 * r, 2)
    return round(-2.0 + 1.2 * (r - 0.5) / 0.5, 2)


def _gap_strong_up(idx: int, total: int) -> float:
    r = _idx_ratio(idx, total)
    base = 0.2 + 0.45 * r
    dip = 0.12 if 0.15 < r < 0.75 and idx % 3 == 1 else 0.0
    return round(base - dip, 2)


def _gap_weak_down(idx: int, total: int) -> float:
    r = _idx_ratio(idx, total)
    base = 0.35 - 0.9 * r
    wobble = 0.1 if 0.25 < r < 0.85 and idx % 4 == 2 else 0.0
    return round(base + wobble, 2)


_GAP_FN = {
    "一路抬升": _gap_rising,
    "一路走弱": _gap_falling,
    "震荡": _gap_flat,
    "尾盘上翘": _gap_late_up,
    "尾盘下压": _gap_late_down,
    "冲高回落": _gap_spike_fade,
    "探底回升": _gap_dip_recover,
    "偏强上行": _gap_strong_up,
    "偏弱下行": _gap_weak_down,
}

MOCK_STOCKS: tuple[MockStock, ...] = (
    MockStock("600519", "贵州茅台", "我的", 1260.0, "一路抬升"),
    MockStock("601318", "中国平安", "我的", 52.0, "一路走弱"),
    MockStock("000001", "平安银行", "我的", 11.0, "震荡"),
    MockStock("300750", "宁德时代", "想买的", 210.0, "尾盘上翘"),
    MockStock("002415", "海康威视", "想买的", 28.0, "尾盘下压"),
    MockStock("002594", "比亚迪", "想买的", 260.0, "冲高回落"),
    MockStock("688981", "中芯国际", "想买的", 85.0, "探底回升"),
    MockStock("600036", "招商银行", "想买的", 38.0, "偏强上行"),
    MockStock("601888", "中国中免", "想买的", 72.0, "偏弱下行"),
)


def mock_stocks() -> list[MockStock]:
    return list(MOCK_STOCKS)


def gap_at_point(stock: MockStock, *, point_idx: int, point_total: int) -> float:
    fn = _GAP_FN.get(stock.expected_shape, _gap_flat)
    return fn(point_idx, point_total)


def _price_from_gap(pre_close: float, gap_pct: float) -> float:
    return round(pre_close * (1 + gap_pct / 100), 3)


def build_mock_snapshots(
    stocks: list[MockStock],
    *,
    point_idx: int,
    point_total: int,
    is_final: bool,
    captured_at: str,
) -> list[AuctionSnap]:
    snaps: list[AuctionSnap] = []
    for stock in stocks:
        gap = gap_at_point(stock, point_idx=point_idx, point_total=point_total)
        price = _price_from_gap(stock.pre_close, gap)
        open_px = price if is_final else None
        trade_px = price
        amount = round(0.05 + 1.45 * _idx_ratio(point_idx, point_total), 4)
        snaps.append(
            AuctionSnap(
                code=stock.code,
                name=stock.name,
                group=stock.group,
                price=price,
                pre_close=stock.pre_close,
                open=open_px,
                open_gap_pct=open_gap_pct(trade_px, stock.pre_close),
                pct_chg=gap,
                amount_yi=amount,
                snapshot_at=captured_at,
            )
        )
    return snaps


def build_mock_series_points(
    schedule: list[datetime],
    *,
    stocks: list[MockStock] | None = None,
) -> list[dict]:
    from quote.auction_snap import snap_to_dict

    profiles = stocks or mock_stocks()
    total = len(schedule)
    points: list[dict] = []
    for idx, scheduled in enumerate(schedule):
        is_final = idx == total - 1
        captured_at = scheduled.strftime("%Y-%m-%d %H:%M:%S")
        snaps = build_mock_snapshots(
            profiles,
            point_idx=idx,
            point_total=total,
            is_final=is_final,
            captured_at=captured_at,
        )
        points.append(
            {
                "captured_at": captured_at,
                "is_final": is_final,
                "rows": [snap_to_dict(s, is_final=is_final) for s in snaps],
            }
        )
    return points
