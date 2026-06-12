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

from morning.checks import (
    build_checks,
    checks_summary_display_segments,
    format_checks_summary_prompt,
    match_verdict,
)
from morning.feeds_fingerprint import decide_feeds_status
from morning.feeds_merge import merge_feeds
from morning.health import build_health
from morning.pre_format import format_stock_prompt_line
from morning.prompt_build import build_morning_user_prompt
from morning.wait_auction import wait_auction_ready
from auction.series import append_auction_series_point
from quote.auction_snap import AuctionSnap
from ai.parse import split_ai_report, codes_in_body, resolve_ai_report_fields
from report.morning_html import build_morning_page
from report.midday_html import build_midday_page


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


class MorningGroupsTest(unittest.TestCase):
    def test_shard_specs_split_large_group(self):
        from morning.groups import build_shard_specs, stocks_for_shard

        ctx = {
            "group_order": ["跌幅达到预期重点关注"],
            "prompt": {
                "stocks": [
                    {"code": f"{i:06d}", "groups": ["跌幅达到预期重点关注"]}
                    for i in range(15)
                ]
            },
        }
        specs = build_shard_specs(ctx)
        self.assertEqual(len(specs), 2)
        self.assertEqual(len(stocks_for_shard(ctx["prompt"]["stocks"], specs[0][0])), 12)
        self.assertEqual(len(stocks_for_shard(ctx["prompt"]["stocks"], specs[1][0])), 3)

    def test_shard_prompt_scoped_rows(self):
        ctx = {
            "meta": {"context_as_of": "2026-06-12 09:25:06", "evening_summary": "摘要"},
            "morning_pre": {"summary": {"refresh": 0, "reuse": 1, "no_new": 0, "failed": 0}},
            "checks": {
                "rows": [
                    {
                        "code": "600519",
                        "name": "茅台",
                        "groups": ["我的"],
                        "primary_stance": "holding",
                        "expected_open": "偏高开",
                        "end_gap": 0.2,
                        "shape_after_920": "震荡",
                        "verdict": "部分符合",
                        "pre_status": "reuse",
                    },
                    {
                        "code": "000021",
                        "name": "深科技",
                        "groups": ["想买的"],
                        "primary_stance": "candidate",
                        "expected_open": "偏低开",
                        "end_gap": 3.0,
                        "shape_after_920": "探底回升",
                        "verdict": "不符合",
                        "pre_status": "reuse",
                    },
                ]
            },
            "open_market": {},
            "evening_expectations": {},
            "prompt": {
                "priority_instructions": "",
                "stocks": [
                    {"code": "600519", "name": "茅台", "groups": ["我的"], "stance_hint": "holding", "tier": "tier0"},
                    {"code": "000021", "name": "深科技", "groups": ["想买的"], "stance_hint": "candidate", "tier": "tier0"},
                ],
            },
            "group_order": ["我的", "想买的"],
        }
        from morning.prompt_build import build_morning_shard_prompt

        holding_prompt = build_morning_shard_prompt(ctx, "我的")
        self.assertIn("600519", holding_prompt)
        self.assertNotIn("000021", holding_prompt)
        self.assertIn("[核对表·本批]", holding_prompt)


class MorningChecksSummaryTest(unittest.TestCase):
    def test_counts_from_rows_when_summary_missing(self):
        checks = {
            "rows": [
                {"verdict": "不符合", "highlight": True},
                {"verdict": "不符合", "highlight": False},
                {"verdict": "符合", "highlight": False},
            ]
        }
        prompt_line = format_checks_summary_prompt(checks)
        self.assertIn("不符合2只", prompt_line)
        self.assertIn("符合1只", prompt_line)
        segs = checks_summary_display_segments(checks)
        self.assertIn("不符合 2", segs)
        self.assertIn("需关注 1", segs)

    def test_env_strip_summary_without_open_market(self):
        html_text = build_morning_page(
            {
                "trade_date": "2026-06-12",
                "session_label": "集合竞价结束",
                "checks": {"summary": {"不符合": 3, "highlight": 2}, "rows": []},
                "open_market": {},
                "ai_ok": False,
                "ai_summary_raw": "",
                "ai_body_raw": "",
            }
        )
        self.assertIn("env-strip", html_text)
        self.assertIn("env-chk", html_text)
        self.assertIn("不符合 3", html_text)


class MorningFeedsTest(unittest.TestCase):
    def test_empty_is_no_new(self):
        merged = merge_feeds({"announcements": []}, {"news": []})
        status, _, _ = decide_feeds_status("600519", merged, prev_baseline=None)
        self.assertEqual(status, "no_new")


class MorningPromptTest(unittest.TestCase):
    def test_merge_fills_empty_discipline_from_expectations(self):
        from morning.evening_ref import merge_evening_into_row

        merged = merge_evening_into_row(
            {"code": "600519", "discipline": ""},
            {"discipline": "不追", "check_925": "看均价"},
        )
        self.assertEqual(merged["discipline"], "不追")
        self.assertEqual(merged["check_925"], "看均价")

    def test_evening_block_uses_checks_expected_open(self):
        from morning.evening_ref import format_evening_stock_block

        block = format_evening_stock_block(
            code="600519",
            name="茅台",
            row={"expected_open": "偏高开"},
            exp_stock={"expected_open": ""},
            tier="tier0",
        )
        self.assertIn("开盘预期=偏高开", block)

    def test_tier0_prompt_line_omits_recap_duplicate(self):
        row = {
            "code": "600010",
            "expected_open": "偏低开",
            "end_gap": -1.2,
            "shape_after_920": "阴",
            "verdict": "符合",
            "pre_status": "reuse",
            "evening_recap": "大利空待核实",
        }
        self.assertNotIn("昨晚=", format_stock_prompt_line(row, include_evening_recap=False))
        self.assertIn("昨晚=", format_stock_prompt_line(row, include_evening_recap=True))

    def test_health_skips_expectation_warn_when_ai_fields_present(self):
        cal = date(2026, 6, 12)
        checks = {
            "rows": [{"code": "600519", "primary_stance": "holding", "expected_open": ""}]
        }
        health = build_health(
            calendar_date=cal,
            auction_trend={"point_count": 21, "stocks": [{"code": "600519"}]},
            morning_pre={"summary": {"failed": 0}, "by_code": {"600519": {"item_counts": {"公告": 1}}}},
            checks=checks,
            open_market={"prev_limit_count": 10, "warnings": []},
            evening_summary="摘要",
            prev_trade_date="2026-06-11",
            evening_expectations={
                "stocks": {
                    "600519": {"ai_fields": {"持仓": "观望为主"}},
                }
            },
        )
        self.assertNotIn("开盘预期缺失", health["health_brief"])

    def test_prompt_line_includes_evening_and_discipline(self):
        row = {
            "code": "600010",
            "expected_open": "偏低开",
            "end_gap": -1.2,
            "shape_after_920": "一路走弱",
            "verdict": "符合",
            "pre_status": "reuse",
            "discipline": "观望等事故结论",
            "evening_recap": "大利空待核实：事故调查中",
        }
        line = format_stock_prompt_line(row)
        self.assertIn("纪律=观望等事故结论", line)
        self.assertIn("昨晚=", line)
        self.assertIn("事故", line)

    def test_evening_expectations_section_in_prompt(self):
        ctx = {
            "meta": {
                "context_as_of": "2026-06-12 09:25:06",
                "calendar_date": "2026-06-12",
                "evening_summary": "【环境】低开",
            },
            "morning_pre": {"summary": {"refresh": 0, "reuse": 1, "no_new": 0, "failed": 0}},
            "checks": {
                "calendar_date": "2026-06-12",
                "rows": [
                    {
                        "code": "600010",
                        "name": "包钢股份",
                        "groups": ["我的"],
                        "primary_stance": "holding",
                        "expected_open": "",
                        "end_gap": -1.29,
                        "shape_after_920": "阴",
                        "verdict": "符合",
                        "pre_status": "reuse",
                        "discipline": "",
                        "check_925": "",
                    }
                ],
            },
            "evening_expectations": {
                "source_trade_date": "2026-06-11",
                "meta": {
                    "l1_axes": {
                        "axes": {
                            "pool": {"signal": "中", "score": 63, "limit_up": 69, "broken_limit": 30},
                            "breadth": {"market_heat": 23.0, "turnover": "2.55万亿", "rise_count": 100, "fall_count": 4000},
                        }
                    },
                    "l2_mainlines": [{"name": "小金属"}],
                },
                "stocks": {
                    "600010": {
                        "expected_open": "",
                        "discipline": "",
                        "check_925": "",
                        "ai_fields": {"大利空·待核实": "板材厂事故仍在调查"},
                        "critical": ["事故调查中"],
                    }
                },
            },
            "prompt": {"priority_instructions": "", "stocks": []},
        }
        prompt = build_morning_user_prompt(ctx)
        self.assertIn("[昨晚结构化预期]", prompt)
        self.assertIn("600010 包钢股份", prompt)
        self.assertIn("板材厂事故", prompt)
        self.assertIn("重大事件=", prompt)
        self.assertIn("池子中", prompt)

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
            "meta": {"context_as_of": "2026-06-12 09:25:06", "calendar_date": "2026-06-12", "evening_summary": "昨晚摘要"},
            "morning_pre": {"summary": {"refresh": 1, "reuse": 0, "no_new": 0, "failed": 0}},
            "checks": {
                "calendar_date": "2026-06-12",
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
            "evening_expectations": {},
            "prompt": {"priority_instructions": "", "stocks": []},
        }
        prompt = build_morning_user_prompt(ctx)
        self.assertIn("[9:15 refresh 明细]", prompt)
        self.assertIn("深科技：测试", prompt)
        self.assertIn("[推送 tier0 须逐只覆盖]", prompt)
        self.assertIn("000021 深科技", prompt)

    def test_user_prompt_includes_prev_limit_and_check_summary(self):
        ctx = {
            "meta": {"context_as_of": "2026-06-12 09:25:06", "calendar_date": "2026-06-12"},
            "morning_pre": {"summary": {"refresh": 0, "reuse": 1, "no_new": 0, "failed": 0}},
            "checks": {
                "summary": {"不符合": 5, "超预期偏强": 2, "highlight": 7},
                "rows": [],
            },
            "open_market": {
                "pool_hint": "维持仓位",
                "prev_limit_count": 69,
                "prev_limit_avg_pct": 1.18,
                "prev_limit_up": 38,
                "prev_limit_down": 30,
                "prev_limit_premium_3pct": 27,
                "index_open_gaps": [{"name": "上证指数", "open_gap_pct": 0.77}],
            },
            "evening_expectations": {},
            "prompt": {"priority_instructions": "", "stocks": []},
        }
        prompt = build_morning_user_prompt(ctx)
        self.assertIn("昨涨停今开", prompt)
        self.assertIn("核对统计", prompt)
        self.assertIn("不符合5只", prompt)
        self.assertIn("上证指数", prompt)


class MorningHealthTest(unittest.TestCase):
    def test_health_brief_uses_morning_data_only(self):
        cal = date(2026, 6, 12)
        checks = {
            "prev_trade_date": "2026-06-11",
            "rows": [
                {"code": "600519", "primary_stance": "holding", "expected_open": ""},
                {"code": "000021", "primary_stance": "candidate", "expected_open": "偏低开"},
            ],
        }
        morning_pre = {
            "summary": {"failed": 1},
            "by_code": {
                "600519": {"item_counts": {"公告": 0}},
                "000021": {"item_counts": {"公告": 2}},
            },
        }
        health = build_health(
            calendar_date=cal,
            auction_trend={"point_count": 1, "stocks": [{"code": "600519"}]},
            morning_pre=morning_pre,
            checks=checks,
            open_market={"warnings": ["指数开盘: timeout"]},
            evening_summary="",
            prev_trade_date="2026-06-11",
        )
        brief = health["health_brief"]
        self.assertIn("昨晚推送摘要缺失", brief)
        self.assertIn("开盘预期缺失", brief)
        self.assertIn("竞价序列不完整", brief)
        self.assertIn("竞价缺 1 只", brief)
        self.assertIn("9:15素材采集失败 1 只", brief)
        self.assertIn("9:25开盘环境采集异常", brief)
        self.assertIn("1 只近3日无公告", brief)
        self.assertNotIn("大盘主力", brief)
        self.assertNotIn("行业资金", brief)
        self.assertNotIn("自选主力", brief)
        self.assertEqual(health["slot"], "morning")


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

    def test_env_strip_shows_check_summary(self):
        html_text = build_morning_page(
            {
                "trade_date": "2026-06-12",
                "context_as_of": "2026-06-12 09:25:06",
                "session_label": "集合竞价结束",
                "checks": {
                    "summary": {"不符合": 12, "超预期偏强": 3, "highlight": 8},
                    "rows": [],
                },
                "open_market": {
                    "prev_limit_count": 69,
                    "prev_limit_avg_pct": 1.18,
                    "prev_limit_premium_3pct": 27,
                    "index_open_gaps": [{"name": "上证指数", "open_gap_pct": 0.77}],
                },
                "ai_ok": True,
                "ai_summary_raw": "【操作】观望。",
                "ai_body_raw": "",
            }
        )
        self.assertIn("env-chk", html_text)
        self.assertIn("不符合 12", html_text)
        self.assertIn("昨涨停均涨", html_text)

    def test_health_bar_shown_when_brief_present(self):
        html_text = build_morning_page(
            {
                "trade_date": "2026-06-12",
                "health_brief": "大盘主力不可用；自选主力可用；1 只近3日无公告。",
                "checks": {"rows": []},
                "open_market": {},
                "ai_ok": True,
                "ai_summary_raw": "",
                "ai_body_raw": "",
            }
        )
        self.assertIn("health-bar", html_text)
        self.assertIn("大盘主力不可用", html_text)


class MiddayHtmlHealthTest(unittest.TestCase):
    def test_health_bar_shown_when_brief_present(self):
        html_text = build_midday_page(
            {
                "trade_date": "2026-06-11",
                "health_brief": "大盘主力不可用；行业资金不可用；17 只近3日无公告。",
                "ai_ok": True,
                "ai_summary_raw": "",
                "ai_body_raw": "",
                "snapshot_rows": [],
                "group_order": [],
            }
        )
        self.assertIn("health-bar", html_text)
        self.assertIn("17 只近3日无公告", html_text)


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
