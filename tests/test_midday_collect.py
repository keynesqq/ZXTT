"""午间采集编排单元测试（离线）。"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from midday.collect import run_collect_midday

_DAY = date(2026, 6, 10)


class TestMiddayCollect(unittest.TestCase):
    def test_skip_network_reuses_existing_quote(self) -> None:
        result = run_collect_midday(on_date=_DAY, force=True, skip_network=True)
        self.assertEqual(result.get("outcome"), "ok")
        self.assertIn(result.get("overall"), ("ok", "warn"))
        self.assertEqual(result.get("code_count"), 31)
        manifest = json.loads(
            (ROOT / "data" / "collect_manifest" / "2026-06-10_midday.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest.get("slot"), "midday")
        self.assertNotIn("cls_articles", manifest.get("sources") or {})
        self.assertEqual(manifest["sources"]["quote_query"]["status"], "ok")

    def test_quote_missing_blocks(self) -> None:
        with patch("midday.collect.quote_query_cache_path") as mock_path:
            mock_path.return_value = ROOT / "data" / "nonexistent_quote.json"
            with patch("midday.collect.load_quote_query_cache", return_value=None):
                result = run_collect_midday(on_date=_DAY, force=True, skip_network=True)
        self.assertEqual(result.get("overall"), "fail")
        self.assertEqual(result.get("reason"), "quote_failed")


if __name__ == "__main__":
    unittest.main()
