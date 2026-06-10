"""news query 单元测试（离线）。"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from feeds.collect import FeedItem
from feeds.feed_warnings import IND_EMPTY, NEWS_EMPTY, RES_EMPTY
from feeds.non_announcement import (
    NonAnnouncementOptions,
    NonAnnouncementResult,
    collect_non_announcement,
    parse_categories,
)
from news.query import NewsQueryOptions, query_news, query_news_for_stock, resolve_query_options
from watchlist.ths_blocks import StockItem


class ParseCategoriesTests(unittest.TestCase):
    def test_default_all(self):
        self.assertEqual(len(parse_categories(None)), 4)

    def test_industry_alias(self):
        cats = parse_categories("news,industry")
        self.assertEqual(cats, frozenset({"news", "industry"}))

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            parse_categories("foo")


class ResolveQueryOptionsTests(unittest.TestCase):
    @mock.patch("news.query.news_cfg")
    def test_defaults_from_config(self, news_cfg):
        news_cfg.return_value = {
            "lookback_days": 3,
            "max_count": 0,
            "industry_enabled": True,
        }
        opts = resolve_query_options()
        self.assertEqual(opts.lookback_days, 3)
        self.assertTrue(opts.industry_enabled)

    def test_invalid_days_raises(self):
        with self.assertRaises(ValueError):
            resolve_query_options(days=0)

    @mock.patch("news.query.news_cfg")
    def test_empty_categories_raises(self, news_cfg):
        news_cfg.return_value = {"lookback_days": 3, "max_count": 0, "industry_enabled": True}
        with self.assertRaises(ValueError):
            resolve_query_options(categories=frozenset(), industry_enabled=True)


class QueryNewsTests(unittest.TestCase):
    def _options(self) -> NewsQueryOptions:
        return NewsQueryOptions(
            lookback_days=3,
            max_count=0,
            end_date=date(2026, 6, 9),
            industry_enabled=True,
            categories=frozenset({"news", "opinions", "research", "industry"}),
        )

    @mock.patch("news.query.collect_non_announcement")
    def test_no_announcements_in_output(self, collect_na):
        collect_na.return_value = NonAnnouncementResult(
            news=[FeedItem("资讯", "测试新闻", "2026-06-09")],
            opinions=[],
            research=[],
            industry_news=[],
        )
        stock = StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1")
        item = query_news_for_stock(stock, options=self._options(), industry="白酒")
        self.assertEqual(item["news_count"], 1)
        self.assertNotIn("announcements", item)
        self.assertIn("title", item["news"][0])

    @mock.patch("news.query.collect_non_announcement")
    def test_skip_industry_no_ind_empty(self, collect_na):
        collect_na.return_value = NonAnnouncementResult()
        opts = NewsQueryOptions(
            lookback_days=3,
            max_count=0,
            end_date=date(2026, 6, 9),
            industry_enabled=False,
            categories=frozenset({"news", "research"}),
        )
        stock = StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1")
        item = query_news_for_stock(stock, options=opts, industry="白酒")
        self.assertEqual(item["industry_news"], [])
        collect_na.assert_called_once()
        call_opts = collect_na.call_args.kwargs["options"]
        self.assertFalse(call_opts.industry_enabled)
        self.assertNotIn("industry", call_opts.categories)

    @mock.patch("news.query.query_news_for_stock")
    @mock.patch("news.query.resolve_query_stocks")
    @mock.patch("news.query.batch_industries", return_value={"600519": "白酒", "000001": ""})
    def test_multi_codes(self, _ind, resolve_stocks, query_one):
        resolve_stocks.return_value = [
            StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1"),
            StockItem(code="000001", name="000001", group="", block_id=""),
        ]
        query_one.side_effect = [
            {"code": "600519", "news_count": 1},
            {"code": "000001", "news_count": 0},
        ]
        rows, path = query_news(["600519", "000001"], options=self._options(), save=False)
        self.assertEqual(len(rows), 2)

    @mock.patch("news.query.ThreadPoolExecutor")
    @mock.patch("news.query.query_news_for_stock")
    @mock.patch("news.query.resolve_query_stocks")
    @mock.patch("news.query.batch_industries", return_value={})
    def test_parallel_when_multiple_stocks(self, _ind, resolve_stocks, query_one, executor_cls):
        resolve_stocks.return_value = [
            StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1"),
            StockItem(code="000001", name="000001", group="", block_id=""),
        ]
        query_one.side_effect = [{"code": "600519"}, {"code": "000001"}]

        class FakePool:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def map(self, fn, iterable):
                return [fn(item) for item in iterable]

        executor_cls.return_value = FakePool()
        with mock.patch("news.query.news_cfg", return_value={"max_workers": 4}):
            with mock.patch("news.query._query_workers", return_value=4):
                rows, path = query_news(["600519", "000001"], options=self._options(), save=False)
        self.assertEqual(len(rows), 2)
        executor_cls.assert_called_once_with(max_workers=4)


class NonAnnouncementCategoriesTests(unittest.TestCase):
    @mock.patch("feeds.non_announcement.fetch_em_research", return_value=[])
    @mock.patch("feeds.non_announcement.fetch_em_news", return_value=[])
    def test_research_only_no_news_empty(self, _news, _res):
        stock = StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1")
        opts = NonAnnouncementOptions(
            end_date=date(2026, 6, 9),
            cfg={"ths_f10": {"enabled": False}},
            unified_lookback_days=3,
            categories=frozenset({"research"}),
        )
        result = collect_non_announcement(stock, industry="", options=opts)
        self.assertTrue(any(w.get("code_key") == RES_EMPTY for w in result.warnings_struct))
        self.assertFalse(any(w.get("code_key") == NEWS_EMPTY for w in result.warnings_struct))

    @mock.patch("feeds.non_announcement.classify_news", return_value="观点")
    @mock.patch("feeds.non_announcement.fetch_em_news")
    def test_news_only_all_classified_opinion_warns(self, fetch_news, _classify):
        fetch_news.return_value = [
            {
                "title": "600519点评",
                "pub_date": "2026-06-09",
                "pub_time": "10:00",
                "source": "证券时报",
                "url": "http://example.com",
                "provider": "东财",
            }
        ]
        stock = StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1")
        opts = NonAnnouncementOptions(
            end_date=date(2026, 6, 9),
            cfg={"ths_f10": {"enabled": False}},
            unified_lookback_days=3,
            categories=frozenset({"news"}),
        )
        result = collect_non_announcement(stock, industry="", options=opts)
        self.assertEqual(result.news, [])
        self.assertTrue(
            any(
                w.get("code_key") == NEWS_EMPTY and w.get("category") == "资讯"
                for w in result.warnings_struct
            )
        )


class IndustryCacheTests(unittest.TestCase):
    @mock.patch("feeds.non_announcement.fetch_em_news")
    def test_same_industry_fetched_once(self, fetch_news):
        fetch_news.return_value = []
        cache: dict = {}
        from threading import Lock

        opts = NonAnnouncementOptions(
            end_date=date(2026, 6, 9),
            cfg={"ths_f10": {"enabled": False}},
            unified_lookback_days=3,
            categories=frozenset({"industry"}),
            industry_news_cache=cache,
            industry_cache_lock=Lock(),
        )
        stocks = [
            StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1"),
            StockItem(code="000858", name="五粮液", group="我的", block_id="b1"),
        ]
        for stock in stocks:
            collect_non_announcement(stock, industry="白酒", options=opts)
        self.assertEqual(fetch_news.call_count, 1)
        self.assertIn("白酒", cache)


class FetchNewsParallelTests(unittest.TestCase):
    @mock.patch("feeds.eastmoney._fetch_news_em")
    def test_name_and_code_keywords_both_queried(self, fetch_em):
        from feeds.eastmoney import fetch_news

        fetch_em.side_effect = lambda kw, **kwargs: [
            {
                "title": f"{kw}新闻",
                "pub_date": "2026-06-09",
                "pub_time": "10:00",
                "source": "东财",
                "url": "",
                "provider": "东财",
            }
        ]
        rows = fetch_news(
            "600519",
            date(2026, 6, 7),
            date(2026, 6, 9),
            name="贵州茅台",
            strict=True,
        )
        self.assertEqual(fetch_em.call_count, 2)
        self.assertGreaterEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
