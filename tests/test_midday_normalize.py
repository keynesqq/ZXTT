"""午间 normalize 单元测试。"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "tests"))

from _intraday_digest_fixture import write_minimal_intraday_digest
from midday.normalize import build_midday_bundle

_DAY = date(2026, 6, 10)


class TestMiddayNormalize(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._digest_path = write_minimal_intraday_digest(_DAY, segment="morning")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._digest_path.unlink(missing_ok=True)

    def test_bundle_no_cls_articles(self) -> None:
        bundle = build_midday_bundle(on_date=_DAY)
        market = bundle.get("market") or {}
        self.assertNotIn("cls_articles", market)
        self.assertEqual((bundle.get("meta") or {}).get("slot"), "midday")
        paths = (bundle.get("meta") or {}).get("paths") or {}
        self.assertNotIn("cls_articles", paths)
        self.assertEqual(len(bundle.get("by_code") or {}), 31)

    def test_bundle_has_intraday_morning(self) -> None:
        bundle = build_midday_bundle(on_date=_DAY)
        meta = bundle.get("meta") or {}
        paths = meta.get("paths") or {}
        self.assertTrue(meta.get("intraday_digest_ok"))
        self.assertIn("intraday_digest_morning", paths)


if __name__ == "__main__":
    unittest.main()
