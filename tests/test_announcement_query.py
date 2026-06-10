import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from announcement.query import (
    AnnouncementQueryOptions,
    query_announcements,
    query_announcements_for_stock,
    resolve_query_options,
    resolve_query_stocks,
)
from feeds.feed_warnings import ANN_EMPTY, ANN_LATEST_FALLBACK
from watchlist.ths_blocks import StockItem


class ResolveQueryOptionsTests(unittest.TestCase):
    @mock.patch("announcement.query.feeds_cfg")
    def test_defaults_from_config(self, feeds_cfg):
        feeds_cfg.return_value = {
            "announcement": {
                "lookback_days": 7,
                "fallback_latest_count": 3,
                "max_count": 10,
            }
        }
        opts = resolve_query_options()
        self.assertEqual(opts.lookback_days, 7)
        self.assertEqual(opts.fallback_latest_count, 0)
        self.assertEqual(opts.max_count, 10)

    @mock.patch("announcement.query.feeds_cfg")
    def test_cli_overrides_config(self, feeds_cfg):
        feeds_cfg.return_value = {"announcement": {"lookback_days": 7}}
        opts = resolve_query_options(days=14, max_count=5, latest=2, on_date=date(2026, 6, 9))
        self.assertEqual(opts.lookback_days, 14)
        self.assertEqual(opts.max_count, 5)
        self.assertEqual(opts.fallback_latest_count, 2)
        self.assertEqual(opts.end_date, date(2026, 6, 9))

    def test_invalid_days_raises(self):
        with self.assertRaises(ValueError):
            resolve_query_options(days=0)


class ResolveQueryStocksTests(unittest.TestCase):
    @mock.patch("announcement.query.watchlist_by_code")
    def test_merges_watchlist_and_arbitrary_codes(self, watchlist_by_code):
        watchlist_by_code.return_value = {
            "600519": StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1"),
        }
        stocks = resolve_query_stocks(["600519", "000001"])
        self.assertEqual([s.code for s in stocks], ["600519", "000001"])
        self.assertEqual(stocks[0].name, "贵州茅台")
        self.assertEqual(stocks[1].group, "")


class QueryAnnouncementsTests(unittest.TestCase):
    @mock.patch("announcement.query.query_announcements_for_stock")
    @mock.patch("announcement.query.resolve_query_stocks")
    @mock.patch("announcement.query.resolve_query_options")
    def test_multi_codes(self, resolve_opts, resolve_stocks, query_one):
        options = AnnouncementQueryOptions(
            lookback_days=3,
            max_count=0,
            fallback_latest_count=5,
            end_date=date(2026, 6, 9),
        )
        resolve_opts.return_value = options
        resolve_stocks.return_value = [
            StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1"),
            StockItem(code="000001", name="平安银行", group="", block_id=""),
        ]
        query_one.side_effect = [
            {"code": "600519", "announcement_count": 2},
            {"code": "000001", "announcement_count": 1},
        ]
        rows, path = query_announcements(["600519", "000001"], options=options, save=False)
        self.assertEqual(len(rows), 2)
        self.assertEqual(query_one.call_count, 2)
        resolve_opts.assert_not_called()

    @mock.patch("announcement.query.fetch_announcement_rows")
    def test_ann_empty_warning(self, fetch_rows):
        from feeds.announcements import AnnouncementFetchResult

        fetch_rows.return_value = AnnouncementFetchResult(
            rows=[],
            warning_code=ANN_EMPTY,
            warning_message="公告：近3日无数据，且无法获取最新3条",
        )
        stock = StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1")
        options = AnnouncementQueryOptions(
            lookback_days=3,
            max_count=0,
            fallback_latest_count=3,
            end_date=date(2026, 6, 9),
        )
        item = query_announcements_for_stock(stock, options)
        self.assertEqual(item["announcement_count"], 0)
        self.assertEqual(item["warning"]["code"], ANN_EMPTY)

    @mock.patch("feeds.announcements.fetch_cninfo_ann", return_value=[])
    @mock.patch("feeds.announcements.fetch_cninfo_latest")
    def test_no_latest_fallback_when_count_zero(self, fetch_latest, _fetch_cninfo):
        from feeds.announcements import fetch_announcement_rows

        result = fetch_announcement_rows(
            "600519",
            start=date(2026, 6, 6),
            end=date(2026, 6, 9),
            lookback_days=3,
            fallback_latest_count=0,
            use_akshare_fallback=False,
        )
        self.assertEqual(result.rows, [])
        self.assertEqual(result.warning_code, ANN_EMPTY)
        self.assertIn("近3日内无公告", result.warning_message or "")
        fetch_latest.assert_not_called()

    @mock.patch("announcement.query.ThreadPoolExecutor")
    @mock.patch("announcement.query.query_announcements_for_stock")
    @mock.patch("announcement.query.resolve_query_stocks")
    def test_parallel_when_multiple_stocks(self, resolve_stocks, query_one, executor_cls):
        options = AnnouncementQueryOptions(
            lookback_days=7,
            max_count=0,
            fallback_latest_count=0,
            end_date=date(2026, 6, 9),
        )
        stocks = [
            StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1"),
            StockItem(code="000001", name="平安银行", group="", block_id=""),
        ]
        resolve_stocks.return_value = stocks
        query_one.side_effect = [
            {"code": "600519", "announcement_count": 1},
            {"code": "000001", "announcement_count": 0},
        ]

        class FakePool:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def map(self, fn, iterable):
                return [fn(item) for item in iterable]

        executor_cls.return_value = FakePool()
        with mock.patch("announcement.query._query_workers", return_value=4):
            rows, path = query_announcements(["600519", "000001"], options=options, save=False)
        self.assertEqual(len(rows), 2)
        executor_cls.assert_called_once_with(max_workers=4)

    @mock.patch("feeds.announcements.fetch_cninfo_ann")
    @mock.patch("feeds.announcements.fetch_cninfo_latest")
    def test_latest_fallback_message_after_max_count(self, fetch_latest, fetch_cninfo):
        from feeds.announcements import fetch_announcement_rows

        fetch_cninfo.return_value = []
        fetch_latest.return_value = [
            {"title": f"公告{i}", "pub_date": "2026-06-09", "pub_time": "10:00"}
            for i in range(5)
        ]
        result = fetch_announcement_rows(
            "600519",
            start=date(2026, 6, 6),
            end=date(2026, 6, 9),
            lookback_days=3,
            fallback_latest_count=5,
            max_count=2,
            use_akshare_fallback=False,
        )
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.warning_code, ANN_LATEST_FALLBACK)
        self.assertIn("已展示最新2条", result.warning_message or "")

    @mock.patch("feeds.announcements.fetch_cninfo_ann", return_value=[])
    @mock.patch("feeds.announcements.fetch_announcements_akshare")
    def test_akshare_fallback_when_cninfo_empty(self, fetch_akshare, _fetch_cninfo):
        from feeds.announcements import fetch_announcement_rows

        fetch_akshare.return_value = [{"title": "东财公告", "pub_date": "2026-06-09"}]
        result = fetch_announcement_rows(
            "600519",
            start=date(2026, 6, 1),
            end=date(2026, 6, 9),
            lookback_days=8,
            fallback_latest_count=3,
            use_akshare_fallback=True,
        )
        self.assertEqual(len(result.rows), 1)
        self.assertIsNone(result.warning_code)
        fetch_akshare.assert_called_once()


if __name__ == "__main__":
    unittest.main()
