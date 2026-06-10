"""午间预处理全链冒烟（离线）。"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from midday.preprocess import run_preprocess_midday

_DAY = date(2026, 6, 10)


class TestMiddayPreprocess(unittest.TestCase):
    def test_preprocess_full_chain_offline(self) -> None:
        result = run_preprocess_midday(on_date=_DAY, force=True)
        self.assertEqual(result.get("outcome"), "ok", result)
        self.assertEqual(result.get("code_count"), 31)
        self.assertEqual(result.get("prompt_stocks"), 31)
        path = Path(result["path"])
        self.assertTrue(path.is_file())
        ctx = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(ctx.get("slot"), "midday")
        self.assertEqual(len(ctx.get("by_code") or {}), 31)
        health = ctx.get("health") or {}
        trust = health.get("trust_flags") or {}
        self.assertNotIn("cls_articles_complete", trust)
        global_items = health.get("global") or []
        self.assertFalse(any("财联社长文" in str(x.get("message", "")) for x in global_items))
        constraints = (ctx.get("market_local") or {}).get("constraints") or []
        self.assertTrue(any("B 层" in c for c in constraints))


if __name__ == "__main__":
    unittest.main()
