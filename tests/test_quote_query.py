import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from quote.query import query_quotes, resolve_query_stocks
from watchlist.ths_blocks import StockItem


class ResolveQueryStocksTests(unittest.TestCase):
    @mock.patch("quote.query.watchlist_by_code")
    def test_merges_watchlist_and_arbitrary_codes(self, watchlist_by_code):
        watchlist_by_code.return_value = {
            "600519": StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1"),
        }
        stocks = resolve_query_stocks(["600519", "000001"])
        self.assertEqual([s.code for s in stocks], ["600519", "000001"])
        self.assertEqual(stocks[0].group, "我的")
        self.assertEqual(stocks[1].group, "")

    @mock.patch("quote.query.dedupe_stocks_by_code")
    @mock.patch("quote.query.build_snapshots")
    @mock.patch("quote.query.load_stocks")
    def test_query_all_watchlist(self, load_stocks, build_snapshots, dedupe):
        raw = [
            StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1"),
            StockItem(code="600519", name="贵州茅台", group="想买的", block_id="b2"),
            StockItem(code="000001", name="平安银行", group="想买的", block_id="b3"),
        ]
        load_stocks.return_value = raw
        dedupe.return_value = [raw[0], raw[2]]
        from quote.snapshot.build import SnapshotRow

        build_snapshots.return_value = [
            SnapshotRow(code="600519", name="贵州茅台", group="我的", block_id="b1", price=1.0),
            SnapshotRow(code="000001", name="平安银行", group="想买的", block_id="b3", price=2.0),
        ]
        rows, path, meta = query_quotes(all_watchlist=True, save=False)
        self.assertEqual(len(rows), 2)
        self.assertIsNone(path)
        self.assertEqual(meta["code_count"], 2)
        self.assertEqual(meta["row_count"], 3)
        dedupe.assert_called_once_with(raw)
        build_snapshots.assert_called_once_with(
            dedupe.return_value,
            fetch_industry=False,
            record_manifest=False,
        )


if __name__ == "__main__":
    unittest.main()
