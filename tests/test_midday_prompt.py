from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from ai.prompts import MIDDAY_STOCK_BODY_FORMAT
from midday.groups import build_shard_specs, stocks_for_group
from midday.prompt_build import build_midday_shard_prompt
from midday.synthesize import _midday_max_tokens


class MiddayPromptTest(unittest.TestCase):
    def test_shard_prompt_by_watchlist_group(self) -> None:
        ctx = {
            "group_order": ["我的", "想买的"],
            "meta": {"context_as_of": "2026-06-11 12:50:00", "code_count": 2},
            "prompt": {
                "global": "session=午间休市",
                "events_block": "## 想买的\n000021: 无",
                "stocks": [
                    {
                        "code": "000021",
                        "name": "深科技",
                        "groups": ["想买的", "高度关注"],
                        "prompt_line": "line",
                    },
                    {
                        "code": "600010",
                        "name": "包钢股份",
                        "groups": ["我的"],
                        "prompt_line": "line2",
                    },
                ],
            },
        }
        out = build_midday_shard_prompt(ctx, "想买的")
        self.assertIn(MIDDAY_STOCK_BODY_FORMAT, out)
        self.assertIn("## 想买的", out)
        self.assertIn("000021", out)
        self.assertNotIn("600010", out)

    def test_build_shard_specs_from_groups(self) -> None:
        ctx = {
            "group_order": ["我的", "想买的"],
            "prompt": {
                "stocks": [
                    {"code": "600010", "groups": ["我的"]},
                    {"code": "000021", "groups": ["想买的", "高度关注"]},
                ]
            },
        }
        specs = build_shard_specs(ctx)
        self.assertEqual([s[0] for s in specs], ["我的", "想买的"])
        self.assertEqual(len(stocks_for_group(ctx["prompt"]["stocks"], "想买的")), 1)

    def test_midday_token_budget_per_stock(self) -> None:
        stocks = [{"code": f"{i:06d}"} for i in range(11)]
        tok = _midday_max_tokens(stocks, cap=12000)
        self.assertGreaterEqual(tok, 600 + 11 * 500)


if __name__ == "__main__":
    unittest.main()
