"""行情快照字段分档：A=AI/报告 daily，B=full 页扩展，C=系统。"""

from __future__ import annotations

SNAPSHOT_TIER_A: tuple[str, ...] = (
    "code",
    "name",
    "group",
    "industry",
    "board",
    "is_st",
    "price",
    "pre_close",
    "open",
    "open_gap_pct",
    "pct_chg",
    "limit_status",
    "consecutive_boards",
    "amount_yi",
    "turnover",
    "amount_ratio",
    "pct_5d",
    "pct_20d",
    "pct_60d",
    "ma5",
    "ma20",
    "ma5_dist",
    "ma20_dist",
    "intraday_shape",
    "snapshot_at",
    "warnings",
)

SNAPSHOT_TIER_B_ONLY: tuple[str, ...] = (
    "high",
    "low",
    "amplitude",
    "pct_ytd",
    "ma60",
    "ma60_dist",
    "pe",
    "pb",
    "total_mv_yi",
    "float_mv_yi",
    "limit_pct",
    "amount_avg_5d_yi",
)

SNAPSHOT_TIER_C: tuple[str, ...] = (
    "quote_fetched_at",
    "data_missing",
    "block_id",
    "pre_open",
    "amount_ratio_stale",
    "near_limit_open",
    "quotes_pending",
)

DAILY_TABLE_COLUMNS: tuple[str, ...] = (
    "code",
    "name",
    "industry",
    "board",
    "price",
    "pre_close",
    "open_gap_pct",
    "open",
    "pct_chg",
    "limit_status",
    "consecutive_boards",
    "amount_yi",
    "turnover",
    "amount_ratio",
    "pct_5d",
    "pct_20d",
    "pct_60d",
    "ma5",
    "ma5_dist",
    "ma20",
    "ma20_dist",
    "intraday_shape",
    "snapshot_at",
)

DAILY_TABLE_INLINE_FROM_A: tuple[str, ...] = ("group", "is_st", "warnings")
