"""晚间采集编排单元测试（离线）。"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from evening.collect import run_collect_evening

_DAY = date(2026, 6, 10)


class TestEveningCollect(unittest.TestCase):
    def test_skip_network_reuses_existing_quote(self) -> None:
        result = run_collect_evening(on_date=_DAY, force=True, skip_network=True)
        self.assertEqual(result.get("outcome"), "ok")
        self.assertIn(result.get("overall"), ("ok", "warn"))
        self.assertEqual(result.get("code_count"), 31)
        self.assertEqual(result.get("row_count"), 35)
        manifest = json.loads(
            (ROOT / "data" / "collect_manifest" / "2026-06-10.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest.get("slot"), "evening")
        self.assertEqual(manifest.get("schema_version"), 1)
        self.assertEqual(manifest["sources"]["quote_query"]["status"], "ok")

    def test_quote_missing_blocks(self) -> None:
        with patch("evening.collect.quote_query_cache_path") as mock_path:
            mock_path.return_value = ROOT / "data" / "nonexistent_quote.json"
            with patch("evening.collect.load_quote_query_cache", return_value=None):
                result = run_collect_evening(on_date=_DAY, force=True, skip_network=True)
        self.assertEqual(result.get("overall"), "fail")
        self.assertEqual(result.get("reason"), "quote_failed")

    def test_evening_refreshes_existing_quote(self) -> None:
        with patch("evening.collect.query_quotes") as mock_q:
            mock_q.return_value = (None, ROOT / "data" / "quote_query_2026-06-10.json", {"code_count": 31})
            result = run_collect_evening(on_date=_DAY, force=True, skip_network=False)
        self.assertEqual(result.get("outcome"), "ok")
        mock_q.assert_called_once()


if __name__ == "__main__":
    unittest.main()
