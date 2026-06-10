import json

import sys

import tempfile

import unittest

from datetime import date

from pathlib import Path

from unittest import mock



ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT / "packages"))



from quote.query_cache import (
    QUOTE_QUERY_SCHEMA_VERSION,
    join_quotes_with_memberships,
    load_joined_quote_rows,
    persist_quote_query,
    quote_query_cache_path,
)

from watchlist.ths_blocks import StockItem





class QuoteQueryCacheTests(unittest.TestCase):

    def test_layered_all_mode(self):

        with tempfile.TemporaryDirectory() as tmp:

            data_dir = Path(tmp)

            with mock.patch("quote.query_cache.DATA_DIR", data_dir):

                day = date(2026, 6, 10)

                structure = [

                    StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1"),

                    StockItem(code="600519", name="贵州茅台", group="想买的", block_id="b2"),

                    StockItem(code="000001", name="平安银行", group="想买的", block_id="b3"),

                ]

                quotes = [

                    {"code": "600519", "name": "贵州茅台", "group": "我的", "price": 1.0},

                    {"code": "000001", "name": "平安银行", "group": "想买的", "price": 2.0},

                ]

                path = persist_quote_query(

                    quotes,

                    mode="all",

                    structure_stocks=structure,

                    on_date=day,

                )

                data = json.loads(path.read_text(encoding="utf-8"))

                self.assertEqual(data["schema_version"], QUOTE_QUERY_SCHEMA_VERSION)

                self.assertEqual(data["code_count"], 2)

                self.assertEqual(data["row_count"], 3)

                self.assertEqual(len(data["memberships"]), 3)

                self.assertIn("structure", data)



    def test_partial_codes_merge_memberships(self):

        with tempfile.TemporaryDirectory() as tmp:

            data_dir = Path(tmp)

            with mock.patch("quote.query_cache.DATA_DIR", data_dir):

                day = date(2026, 6, 10)

                path = persist_quote_query(

                    [{"code": "600519", "price": 1.0}],

                    mode="all",

                    structure_stocks=[

                        StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1"),

                        StockItem(code="000001", name="平安银行", group="想买的", block_id="b2"),

                    ],

                    on_date=day,

                )

                persist_quote_query(

                    [{"code": "000001", "price": 2.0}],

                    mode="codes",

                    structure_stocks=[

                        StockItem(code="000001", name="平安银行", group="想买的", block_id="b2"),

                    ],

                    on_date=day,

                )

                data = json.loads(path.read_text(encoding="utf-8"))

                self.assertEqual(data["code_count"], 2)

                self.assertEqual(data["row_count"], 2)



    def test_all_mode_dedupes_duplicate_memberships(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            with mock.patch("quote.query_cache.DATA_DIR", data_dir):
                day = date(2026, 6, 10)
                dup = StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1")
                structure = [dup, dup, StockItem(code="000001", name="平安银行", group="想买的", block_id="b2")]
                path = persist_quote_query(
                    [{"code": "600519", "price": 1.0}, {"code": "000001", "price": 2.0}],
                    mode="all",
                    structure_stocks=structure,
                    on_date=day,
                )
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(data["row_count"], 2)
                self.assertEqual(len(data["memberships"]), 2)

    def test_structure_payload_dedupes_before_structure(self):
        dup = StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1")
        stocks = [dup, dup, StockItem(code="000001", name="平安银行", group="想买的", block_id="b2")]
        from quote.query_cache import structure_payload_from_stocks

        memberships, structure = structure_payload_from_stocks(stocks)
        self.assertEqual(len(memberships), 2)
        self.assertEqual(
            sum(len(g.get("stocks") or []) for g in structure.get("groups") or []),
            2,
        )

    def test_load_joined_quote_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            with mock.patch("quote.query_cache.DATA_DIR", data_dir):
                day = date(2026, 6, 10)
                from quote.query_cache import load_joined_quote_rows

                persist_quote_query(
                    [{"code": "600519", "price": 10.0, "name": "贵州茅台"}],
                    mode="all",
                    structure_stocks=[
                        StockItem(code="600519", name="贵州茅台", group="我的", block_id="b1"),
                        StockItem(code="600519", name="贵州茅台", group="想买的", block_id="b2"),
                    ],
                    on_date=day,
                )
                rows = load_joined_quote_rows(on_date=day)
                self.assertIsNotNone(rows)
                assert rows is not None
                self.assertEqual(len(rows), 2)
                self.assertEqual({r["group"] for r in rows}, {"我的", "想买的"})

    def test_join_quotes_with_memberships(self):

        quotes = [{"code": "600519", "price": 10.0, "name": "贵州茅台"}]

        memberships = [

            {"code": "600519", "name": "贵州茅台", "group": "我的"},

            {"code": "600519", "name": "贵州茅台", "group": "想买的"},

        ]

        rows = join_quotes_with_memberships(quotes, memberships)

        self.assertEqual(len(rows), 2)

        self.assertEqual({r["group"] for r in rows}, {"我的", "想买的"})

        self.assertEqual(rows[0]["price"], 10.0)





if __name__ == "__main__":

    unittest.main()


