from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from ai.prompts import MIDDAY_STOCK_BODY_FORMAT
from midday.prompt_build import build_midday_shard_prompt
from midday.synthesize import _midday_max_tokens


class MiddayPromptTest(unittest.TestCase):
    def test_shard_prompt_includes_unified_body_format(self) -> None:
        ctx = {
            "meta": {"context_as_of": "2026-06-11 12:50:00", "code_count": 1},
            "prompt": {
                "global": "session=午间休市",
                "events_block": "## candidate\n000021: 无",
                "stocks": [{"code": "000021", "name": "深科技", "stance_hint": "候选", "prompt_line": "line"}],
            },
        }
        out = build_midday_shard_prompt(ctx, "candidate")
        self.assertIn(MIDDAY_STOCK_BODY_FORMAT, out)
        self.assertIn("上午复盘", out)

    def test_midday_token_budget_per_stock(self) -> None:
        stocks = [{"code": f"{i:06d}"} for i in range(11)]
        tok = _midday_max_tokens(stocks, cap=12000)
        self.assertGreaterEqual(tok, 600 + 11 * 500)


if __name__ == "__main__":
    unittest.main()
