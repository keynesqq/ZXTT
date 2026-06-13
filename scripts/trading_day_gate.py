"""计划任务入口：今日非交易日则输出 SKIP（仍 exit 0，避免任务计划程序报失败）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from core.trading_calendar import is_trading_day, today_cn  # noqa: E402


def main() -> int:
    d = today_cn()
    if is_trading_day(d):
        print("RUN")
        return 0
    print("SKIP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
