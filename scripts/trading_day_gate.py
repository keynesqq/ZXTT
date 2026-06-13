"""计划任务入口：按 slot 判断是否 RUN；SKIP 仍 exit 0，避免任务计划程序报失败。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from core.trading_calendar import is_trading_day, should_run_evening, should_run_eve_news, today_cn  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="计划任务交易日门禁")
    parser.add_argument(
        "--slot",
        default="intraday",
        choices=("intraday", "evening", "eve-news"),
        help="intraday=当天交易日；evening=当天交易日；eve-news=交易日前夜（今日休市、明日开盘）",
    )
    args = parser.parse_args()
    d = today_cn()
    if args.slot == "evening":
        ok = is_trading_day(d)
    elif args.slot == "eve-news":
        ok = should_run_eve_news(d)
    else:
        ok = is_trading_day(d)
    print("RUN" if ok else "SKIP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
