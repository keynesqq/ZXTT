"""午间预处理全链冒烟（离线）。"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "tests"))

from _intraday_digest_fixture import write_minimal_intraday_digest
from midday.preprocess import run_preprocess_midday

_DAY = date(2026, 6, 10)


class TestMiddayPreprocess(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._digest_path = write_minimal_intraday_digest(_DAY, segment="morning")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._digest_path.unlink(missing_ok=True)

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
        self.assertFalse(any(x.get("code_key") == "INTRADAY_DIGEST_MISSING" for x in global_items))
        constraints = (ctx.get("market_local") or {}).get("constraints") or []
        self.assertTrue(any("B 层" in c for c in constraints))


class TestMiddayPreprocessSoftDegrade(unittest.TestCase):
    def test_preprocess_ok_without_intraday_digest(self) -> None:
        from core.paths import DATA_DIR

        path = DATA_DIR / f"intraday_digest_{_DAY.isoformat()}_morning.json"
        backup = path.read_text(encoding="utf-8") if path.is_file() else None
        if path.is_file():
            path.unlink()
        try:
            result = run_preprocess_midday(on_date=_DAY, force=True)
            self.assertEqual(result.get("outcome"), "ok", result)
            ctx = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
            global_items = (ctx.get("health") or {}).get("global") or []
            missing = [x for x in global_items if x.get("code_key") == "INTRADAY_DIGEST_MISSING"]
            self.assertEqual(len(missing), 1)
            self.assertEqual(missing[0].get("level"), "warn")
            stocks = (ctx.get("prompt") or {}).get("stocks") or []
            self.assertTrue(stocks)
            self.assertIn("上午监控未采集", stocks[0].get("prompt_line") or "")
            self.assertIn("intraday_monitor=不可用", (ctx.get("prompt") or {}).get("global") or "")
        finally:
            if backup is not None:
                path.write_text(backup, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
