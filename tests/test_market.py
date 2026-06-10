"""market 大盘情绪单元测试（离线）。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from collect.manifest import load_manifest
from market.cls.daily_articles import (
    ARTICLE_SLOTS,
    _match_slot,
    before_typical_article_publish,
    incomplete_articles_hint,
)
from market.sentiment import (
    _cls_articles_payload_ok,
    _collect_cls_articles_resolved,
    _score_emotion,
    _should_collect_cls_articles,
    collect_market_sentiment,
    load_limit_meta_map,
    load_market_sentiment,
)


class ScoreEmotionTests(unittest.TestCase):
    def test_strong_prev_avg_raises_score(self):
        score, label, _ = _score_emotion(
            zt_count=50,
            broken_count=10,
            prev_avg=2.5,
            prev_up_ratio=0.8,
            prev_green_high_ratio=0.5,
            broken_repair_ratio=0.6,
        )
        self.assertGreaterEqual(score, 72)
        self.assertEqual(label, "强")

    def test_weak_prev_avg_lowers_score(self):
        score, label, _ = _score_emotion(
            zt_count=20,
            broken_count=30,
            prev_avg=-2.0,
            prev_up_ratio=0.2,
            prev_green_high_ratio=0.1,
            broken_repair_ratio=0.1,
        )
        self.assertLessEqual(score, 40)
        self.assertEqual(label, "防守")


class ClsArticlesGateTests(unittest.TestCase):
    def test_payload_ok_requires_all_slots(self):
        self.assertFalse(_cls_articles_payload_ok({"found_count": 2, "skipped": False}))
        self.assertTrue(
            _cls_articles_payload_ok({"found_count": len(ARTICLE_SLOTS), "skipped": False})
        )

    def test_subject_candidates_match_all_five_slots(self):
        from market.cls.daily_articles import match_from_candidates

        d = date(2026, 6, 9)
        ts = int(datetime(2026, 6, 9, 15, 0, 0).timestamp())
        candidates = [
            {"id": "2394851", "title": "【每日收评】沪指收涨", "ctime": ts},
            {"id": "2394913", "title": "【数据看盘】资金动向", "ctime": ts},
            {"id": "2394903", "title": "【焦点复盘】指数回升", "ctime": ts},
            {"id": "2394739", "title": "6月9日涨停分析", "ctime": ts},
            {"id": "2394750", "title": "今日投资舆情热点", "ctime": ts},
        ]
        matched = match_from_candidates(candidates, trade_date=d)
        self.assertEqual(len(matched), len(ARTICLE_SLOTS))

    def test_ids_to_scan_is_bounded(self):
        from market.cls.daily_articles import _MAX_GAP_SCAN, _ids_to_scan

        candidates = [
            {"id": "2394913", "ctime": int(datetime(2026, 6, 9, 17, 0, 0).timestamp())},
            {"id": "2394903", "ctime": int(datetime(2026, 6, 9, 17, 0, 0).timestamp())},
        ]
        ids = _ids_to_scan(candidates, date(2026, 6, 9))
        self.assertLessEqual(len(ids), _MAX_GAP_SCAN)

    def test_match_slot_bare_afternoon_titles(self):
        d = date(2026, 6, 9)
        limit_slot = next(s for s in ARTICLE_SLOTS if s["key"] == "limit_up_analysis")
        hot_slot = next(s for s in ARTICLE_SLOTS if s["key"] == "sentiment_hot")
        self.assertTrue(_match_slot("6月9日涨停分析", limit_slot, trade_date=d))
        self.assertTrue(_match_slot("今日投资舆情热点", hot_slot, trade_date=d))
        self.assertFalse(_match_slot("【VIP】涨停分析", limit_slot, trade_date=d))

    def test_should_collect_articles_only_when_requested(self):
        cfg = {"cls_articles_enabled": True}
        self.assertFalse(_should_collect_cls_articles(False, cfg))
        self.assertTrue(_should_collect_cls_articles(True, cfg))


class ClsArticlesRetryTests(unittest.TestCase):
    def test_resolved_retries_when_incomplete(self):
        trade = date(2026, 6, 5)
        first = {"found_count": 2, "articles": {}, "skipped": False}
        second = {"found_count": 5, "articles": {"a": 1}, "skipped": False}
        with (
            mock.patch("market.cls.daily_articles.before_typical_article_publish", return_value=False),
            mock.patch(
                "market.sentiment._cls_articles_payload_ok",
                side_effect=[False, True],
            ),
            mock.patch(
                "market.cls.daily_articles.collect_cls_daily_articles",
                side_effect=[first, second],
            ) as collect,
        ):
            out = _collect_cls_articles_resolved(trade)
        self.assertEqual(out["found_count"], 5)
        self.assertEqual(collect.call_count, 2)
        collect.assert_any_call(for_date=trade, force=True, calendar_date=None)


class LoadLimitMetaMapTests(unittest.TestCase):
    def test_merges_limit_up_and_broken_index(self):
        payload = {
            "limit_up_index": {
                "600519": {"lb_count": 3, "broken_count": 0, "industry": "白酒"},
            },
            "broken_limit_index": {
                "000001": {"broken_count": 2, "pct_chg": 1.2, "industry": "银行"},
                "600519": {"broken_count": 1, "pct_chg": -0.5, "industry": ""},
            },
        }
        with (
            mock.patch("market.sentiment.load_market_sentiment", return_value=payload),
            mock.patch("market.sentiment._STORAGE", Path("/tmp")),
        ):
            meta = load_limit_meta_map(date(2026, 6, 9))
        self.assertTrue(meta["600519"]["in_limit_up_pool"])
        self.assertEqual(meta["600519"]["consecutive_boards"], 3)
        self.assertEqual(meta["000001"]["broken_count"], 2)


class CollectMarketSentimentTests(unittest.TestCase):
    def _zt_row(self, code: str, name: str, lb: int = 1) -> dict:
        return {
            "code": code,
            "name": name,
            "pct_chg": 10.0,
            "industry": "测试",
            "lb_count": lb,
            "broken_count": 0,
        }

    def test_collect_writes_json_and_manifest(self):
        trade = date(2026, 6, 9)
        zt = [self._zt_row("600519", "贵州茅台", 2)]
        broken = [self._zt_row("000001", "平安银行")]
        prev = [{"code": "000002", "name": "万科", "pct_chg": 1.5, "industry": "地产", "lb_count": 1}]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with (
                mock.patch("market.sentiment._STORAGE", tmp_path / "market_sentiment"),
                mock.patch("collect.manifest.ROOT", tmp_path),
                mock.patch("market.sentiment._fetch_pool", side_effect=[zt, broken]),
                mock.patch("market.sentiment._prev_pool", return_value=prev),
                mock.patch(
                    "market.sentiment.market_cfg",
                    return_value={"enabled": True},
                ),
            ):
                data = collect_market_sentiment(trade, calendar_date=trade)
                out_path = tmp_path / "market_sentiment" / f"{trade.isoformat()}.json"
                self.assertTrue(out_path.is_file())
                saved = json.loads(out_path.read_text(encoding="utf-8"))
                self.assertEqual(saved["limit_up_count"], 1)
                self.assertEqual(saved["broken_limit_count"], 1)
                self.assertNotIn("cls", saved)
                self.assertEqual(data["pool_signal"], saved["pool_signal"])
                self.assertEqual(data["pool_score"], saved["pool_score"])
                self.assertEqual(data["emotion_label"], saved["pool_signal"])

                manifest = load_manifest(trade)
                assert manifest is not None
                pool = manifest["sources"]["akshare_zt_pool"]
                self.assertTrue(pool["ok"])
                self.assertEqual(pool["limit_up_count"], 1)
                self.assertIn("duration_ms", pool)

    def test_empty_all_pools_marks_manifest_not_ok(self):
        trade = date(2026, 6, 9)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with (
                mock.patch("market.sentiment._STORAGE", tmp_path / "market_sentiment"),
                mock.patch("collect.manifest.ROOT", tmp_path),
                mock.patch("market.sentiment._fetch_pool", return_value=[]),
                mock.patch("market.sentiment._prev_pool", return_value=[]),
                mock.patch(
                    "market.sentiment.market_cfg",
                    return_value={"enabled": True},
                ),
            ):
                collect_market_sentiment(trade, calendar_date=trade)
                manifest = load_manifest(trade)
            assert manifest is not None
            pool = manifest["sources"]["akshare_zt_pool"]
            self.assertFalse(pool["ok"])
            self.assertTrue(pool.get("empty_all_pools"))

    def test_disabled_skips_without_collect(self):
        trade = date(2026, 6, 9)
        with mock.patch(
            "market.sentiment.market_cfg",
            return_value={"enabled": False},
        ):
            data = collect_market_sentiment(trade, calendar_date=trade)
        self.assertIn("market.enabled=false", data["warnings"][0])
        self.assertEqual(data["pool_signal"], "不明")

    def test_load_market_sentiment_reads_saved_file(self):
        trade = date(2026, 6, 9)
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp) / "market_sentiment"
            storage.mkdir(parents=True)
            payload = {"date": trade.isoformat(), "limit_up_count": 42}
            (storage / f"{trade.isoformat()}.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            with mock.patch("market.sentiment._STORAGE", storage):
                loaded = load_market_sentiment(trade)
            self.assertEqual(loaded["limit_up_count"], 42)


class ClsArticlesHintTests(unittest.TestCase):
    def test_before_cutoff_flag(self):
        d = date(2026, 6, 9)
        tz = __import__("zoneinfo").ZoneInfo("Asia/Shanghai")
        now = __import__("datetime").datetime(2026, 6, 9, 15, 0, tzinfo=tz)
        self.assertTrue(before_typical_article_publish(d, now=now))

    def test_incomplete_hint_before_cutoff(self):
        d = date(2026, 6, 9)
        tz = __import__("zoneinfo").ZoneInfo("Asia/Shanghai")
        now = __import__("datetime").datetime(2026, 6, 9, 15, 0, tzinfo=tz)
        hint = incomplete_articles_hint(d, 2, 5, now=now)
        self.assertIn("可能尚未发布", hint or "")
        self.assertIn("2/5", hint or "")


if __name__ == "__main__":
    unittest.main()
