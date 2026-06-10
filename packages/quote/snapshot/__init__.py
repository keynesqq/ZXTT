"""行情构建（供 quote query 复用，不含报告 snapshot 采集）。"""

from quote.snapshot.build import SnapshotRow, build_snapshots, snapshot_row_dict

__all__ = ["SnapshotRow", "build_snapshots", "snapshot_row_dict"]
