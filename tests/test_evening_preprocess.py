"""晚间预处理全链冒烟（离线，跳 cls 重采）。"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from evening.preprocess import run_preprocess_evening

_DAY = date(2026, 6, 10)


import unittest


class TestEveningPreprocess(unittest.TestCase):
    def test_preprocess_full_chain_offline(self) -> None:
        result = run_preprocess_evening(on_date=_DAY, force=True, skip_cls_recollect=True)
        self.assertEqual(result.get("outcome"), "ok", result)
        self.assertEqual(result.get("code_count"), 31)
        self.assertEqual(result.get("prompt_stocks"), 31)
        path = Path(result["path"])
        self.assertTrue(path.is_file())
        ctx = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(ctx.get("by_code") or {}), 31)
        self.assertTrue(ctx.get("prompt", {}).get("stocks"))
        self.assertTrue(ctx.get("meta", {}).get("context_as_of"))
        self.assertIn("health", ctx)
        self.assertIn("market_local", ctx)


if __name__ == "__main__":
    unittest.main()
