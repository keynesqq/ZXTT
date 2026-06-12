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
from morning.pre_format import format_stock_prompt_line
from morning.prompt_build import build_morning_user_prompt
from morning.wait_auction import wait_auction_ready
from auction.series import append_auction_series_point
from quote.auction_snap import AuctionSnap
from ai.parse import split_ai_report, codes_in_body, resolve_ai_report_fields
from report.morning_html import build_morning_page


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


class MorningPromptTest(unittest.TestCase):
    def test_prompt_line_includes_refresh_titles(self):
        row = {
            "code": "000021",
            "expected_open": "偏低开",
            "end_gap": 3.43,
            "shape_after_920": "探底回升",
            "verdict": "不符合",
            "pre_status": "refresh",
            "pre_titles": ["观点:深科技：公司一直密切关注客户动态"],
        }
        line = format_stock_prompt_line(row)
        self.assertIn("新素材=", line)
        self.assertIn("深科技", line)

    def test_user_prompt_lists_refresh_and_tier0(self):
        ctx = {
            "meta": {"context_as_of": "2026-06-12 09:25:06", "evening_summary": "昨晚摘要"},
            "morning_pre": {"summary": {"refresh": 1, "reuse": 0, "no_new": 0, "failed": 0}},
            "checks": {
                "rows": [
                    {
                        "code": "000021",
                        "name": "深科技",
                        "groups": ["想买的"],
                        "primary_stance": "candidate",
                        "expected_open": "偏低开",
                        "end_gap": 3.43,
                        "shape_after_920": "探底回升",
                        "verdict": "不符合",
                        "pre_status": "refresh",
                        "pre_titles": ["观点:深科技：测试"],
                    }
                ]
            },
            "prompt": {"priority_instructions": "", "stocks": []},
        }
        prompt = build_morning_user_prompt(ctx)
        self.assertIn("[9:15 refresh 明细]", prompt)
        self.assertIn("深科技：测试", prompt)
        self.assertIn("[推送 tier0 须逐只覆盖]", prompt)
        self.assertIn("000021 深科技", prompt)


class MorningHtmlTest(unittest.TestCase):
    def test_page_integrates_checks_into_report(self):
        html_text = build_morning_page(
            {
                "trade_date": "2026-06-12",
                "context_as_of": "2026-06-12 09:25:06",
                "checks": {
                    "rows": [
                        {
                            "code": "000021",
                            "name": "深科技",
                            "groups": ["想买的"],
                            "expected_open": "偏低开",
                            "end_gap": 3.43,
                            "shape_after_920": "探底回升",
                            "verdict": "不符合",
                            "pre_status": "refresh",
                            "pre_titles": ["观点:深科技：测试"],
                        }
                    ]
                },
                "open_market": {
                    "index_open_gaps": [{"name": "上证指数", "open_gap_pct": -0.03}]
                },
                "group_order": ["想买的", "其它"],
                "membership_rows": [{"code": "000021", "group": "想买的", "name": "深科技"}],
                "ai_ok": True,
                "ai_summary_raw": "【环境】低开\n【操作】观望",
                "ai_body_raw": (
                    "### 000021 深科技\n"
                    "（想买的）核对预期为偏低开，实际高开。\n"
                    "verdict：不符合预期偏强\n"
                ),
            }
        )
        self.assertNotIn("昨晚推送摘要", html_text)
        self.assertIn("env-strip", html_text)
        self.assertIn("竞价大盘", html_text)
        self.assertIn("正式报告", html_text)
        self.assertIn("check-heading-inline", html_text)
        self.assertNotIn("stock-fact-inline", html_text)
        self.assertNotIn("SLA", html_text)
        self.assertNotIn("check-strip", html_text)
        self.assertIn("偏低开", html_text)
        self.assertNotIn("（想买的）", html_text)
        self.assertNotIn("verdict：", html_text)
        self.assertIn("核对预期为偏低开", html_text)
        self.assertNotIn("9:15 素材", html_text)
        self.assertNotIn("观点:深科技：测试", html_text)
        self.assertNotIn("核对表", html_text)


class WaitAuctionRebuildTest(unittest.TestCase):
    def test_rebuild_trend_from_series_without_manifest_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            day = date(2026, 6, 12)
            with (
                patch("morning.wait_auction.DATA_DIR", data),
                patch("auction.series.DATA_DIR", data),
                patch("auction.trajectory.DATA_DIR", data),
            ):
                snap = AuctionSnap(code="600519", name="茅台", group="", pct_chg=0.5)
                append_auction_series_point(
                    [snap],
                    captured_at="2026-06-12 09:15:00",
                    on_date=day,
                )
                append_auction_series_point(
                    [snap],
                    captured_at="2026-06-12 09:25:00",
                    on_date=day,
                    is_final=True,
                )
                ok, _manifest = wait_auction_ready(day, max_sec=0.1)
                self.assertTrue(ok)
                self.assertTrue((data / f"auction_trend_{day.isoformat()}.json").is_file())


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
