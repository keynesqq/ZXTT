"""晚间 3.1 合并对齐单元测试（离线，2026-06-10 基线）。"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from evening.normalize import build_evening_bundle

_DAY = date(2026, 6, 10)


class TestEveningNormalize(unittest.TestCase):
    def test_build_bundle_baseline(self) -> None:
        bundle = build_evening_bundle(on_date=_DAY)
        meta = bundle["meta"]
        self.assertEqual(meta["code_count"], 31)
        self.assertEqual(meta["row_count"], 35)
        self.assertEqual(len(bundle["by_code"]), 31)
        self.assertIn("600519", meta["orphan_codes"])
        dual = bundle["by_code"]["600021"]
        self.assertEqual(len(dual["groups"]), 2)
        self.assertNotIn("group", dual["quote"])
        self.assertIn("feeds_merged", dual)
        self.assertIn("公告", dual["feeds_merged"])
        self.assertIn("market", bundle)
        self.assertIn("flow_meta", bundle["market"])
        self.assertTrue(meta["context_as_of"])


if __name__ == "__main__":
    unittest.main()
