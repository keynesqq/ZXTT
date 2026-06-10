"""午间 normalize 单元测试。"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from midday.normalize import build_midday_bundle

_DAY = date(2026, 6, 10)


class TestMiddayNormalize(unittest.TestCase):
    def test_bundle_no_cls_articles(self) -> None:
        bundle = build_midday_bundle(on_date=_DAY)
        market = bundle.get("market") or {}
        self.assertNotIn("cls_articles", market)
        self.assertEqual((bundle.get("meta") or {}).get("slot"), "midday")
        paths = (bundle.get("meta") or {}).get("paths") or {}
        self.assertNotIn("cls_articles", paths)
        self.assertEqual(len(bundle.get("by_code") or {}), 31)


if __name__ == "__main__":
    unittest.main()
