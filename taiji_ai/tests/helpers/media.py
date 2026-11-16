"""Test-only edits of a stored recording (never used by the code under test)."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def tamper_pts(rec_dir: Path, *, shift_s: float = 0.0, drop_last: int = 0) -> None:
    """Make ``pts.parquet`` disagree with the video: shift every ``t_sec`` [s], or drop the last rows."""
    path = rec_dir / "pts.parquet"
    table = pq.read_table(path)
    metadata = table.schema.metadata
    if drop_last:
        table = table.slice(0, table.num_rows - drop_last)
    if shift_s:
        field = table.schema.field("t_sec")
        table = table.set_column(
            table.schema.get_field_index("t_sec"), field, pa.array(table["t_sec"].to_numpy() + shift_s, type=field.type)
        )
    pq.write_table(table.replace_schema_metadata(metadata), path)
