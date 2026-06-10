import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from core.query_cache import code_merge_key, write_query_cache


class QueryCacheTests(unittest.TestCase):
    def test_merge_by_code_same_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            with mock.patch("core.query_cache.DATA_DIR", data_dir):
                day = date(2026, 6, 10)
                write_query_cache(
                    "announcement_query",
                    payload_key="items",
                    items=[{"code": "600519", "announcement_count": 1}],
                    query_meta={"end_date": day.isoformat()},
                    on_date=day,
                    merge_key_fn=code_merge_key,
                )
                path = write_query_cache(
                    "announcement_query",
                    payload_key="items",
                    items=[{"code": "000001", "announcement_count": 2}],
                    query_meta={"end_date": day.isoformat()},
                    on_date=day,
                    merge_key_fn=code_merge_key,
                )
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(data["count"], 2)
                codes = {row["code"] for row in data["items"]}
                self.assertEqual(codes, {"600519", "000001"})

if __name__ == "__main__":
    unittest.main()
