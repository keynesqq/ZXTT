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
from ai.parse import split_ai_report, codes_in_body, resolve_ai_report_fields


class MorningChecksTest(unittest.TestCase):
    def test_match_verdict_high_open(self):
        self.assertEqual(match_verdict("偏高开", 1.8), "超预期偏强")
        self.assertEqual(match_verdict("偏高开", 0.4), "符合")

    def test_match_verdict_weak_surprise(self):
        self.assertEqual(match_verdict("", -1.51), "超预期偏弱")
        self.assertEqual(match_verdict("偏高开", -1.8), "不符合")

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


class MorningParseTest(unittest.TestCase):
    def test_split_summary_and_body_with_stock_headings(self):
        raw = (
            "## 推送摘要\n"
            "【环境】低开\n"
            "【操作】观望\n\n"
            "---\n\n"
            "### 600519 贵州茅台\n"
            "竞价小低开。\n"
        )
        body, summary = split_ai_report(raw)
        self.assertIn("【环境】", summary)
        self.assertNotIn("### 600519", summary)
        self.assertIn("### 600519", body)
        self.assertEqual(codes_in_body(body), ["600519"])

    def test_resolve_fields_from_raw_when_body_empty(self):
        raw = (
            "## 推送摘要\n"
            "【环境】低开\n\n"
            "---\n\n"
            "### 600519 贵州茅台\n"
            "竞价小低开。\n"
        )
        fields = resolve_ai_report_fields(
            raw=raw,
            body="",
            summary="",
            stocks=[{"code": "600519"}],
        )
        self.assertIn("### 600519", fields["body"])
        self.assertIn("【环境】", fields["summary"])
        self.assertEqual(fields["missing_codes"], [])


if __name__ == "__main__":
    unittest.main()
