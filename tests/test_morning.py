from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from morning.checks import build_checks, match_verdict
from morning.feeds_fingerprint import decide_feeds_status
from morning.feeds_merge import merge_feeds


class MorningChecksTest(unittest.TestCase):
    def test_match_verdict_high_open(self):
        self.assertEqual(match_verdict("偏高开", 1.8), "超预期")
        self.assertEqual(match_verdict("偏高开", 0.4), "符合")

    def test_build_checks_row(self):
        cal = date(2026, 6, 10)
        auction = {
            "point_count": 3,
            "stocks": [
                {
                    "code": "600519",
                    "name": "茅台",
                    "end_gap": 1.2,
                    "shape": "一路抬升",
                    "shape_after_920": "一路抬升",
                    "limit_status": "正常",
                }
            ],
        }
        morning_pre = {
            "by_code": {
                "600519": {"status": "reuse", "new_titles": []},
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            exp_dir = data / "expectations"
            exp_dir.mkdir()
            ai_dir = data / "scheduled_ai"
            ai_dir.mkdir()
            exp_dir.joinpath("2026-06-10.json").write_text(
                json.dumps(
                    {
                        "stocks": {
                            "600519": {
                                "expected_open": "偏高开",
                                "discipline": "不追",
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch("morning.checks._EXP_DIR", exp_dir), patch(
                "morning.checks._AI_DIR", ai_dir
            ), patch("morning.checks.load_quote_query_cache", return_value={"memberships": []}):
                checks = build_checks(
                    calendar_date=cal,
                    auction_trend=auction,
                    morning_pre=morning_pre,
                )
        rows = checks.get("rows") or []
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["verdict"], "符合")
        self.assertEqual(rows[0]["code"], "600519")


class MorningFeedsTest(unittest.TestCase):
    def test_empty_is_no_new(self):
        merged = merge_feeds({"announcements": []}, {"news": []})
        status, _, _ = decide_feeds_status("600519", merged, prev_baseline=None)
        self.assertEqual(status, "no_new")


if __name__ == "__main__":
    unittest.main()
