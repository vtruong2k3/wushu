"""T-IO-20, T-IO-21, T-IO-22: a clip trimmed on a phone (BUG-0052).

A stream copy that starts between two keyframes has an edit list.
The packets before the edit start stay in the file with
negative times and the flag "discard"; the decoder never outputs them. They are not frames, so the frame table of the
recording (``pts.parquet``), ``n_frames`` and the proxy check must count the decoded frames only.
"""

from __future__ import annotations

import av
import numpy as np
import pyarrow.parquet as pq
import pytest

from taiji_ai.io.frames import scan_pts_ticks
from taiji_ai.io.ingest import ingest_recording
from taiji_ai.io.proxy import make_proxy

TRIMMED = ["trimmed_video", "trimmed_mov"]
EVERY_VIDEO = [
    "cfr_video",
    "vfr_video",
    "rotated_video",
    "one_frame_video",
    "offset_video",
    "coarse_cfr_30",
    "coarse_cfr_2997",
    "dropped_frame_video",
    *TRIMMED,
]


def _decoded_pts(path) -> np.ndarray:
    """The timestamps (ticks) of the frames the decoder really outputs: the oracle for the packet scan."""
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        return np.sort(np.array([f.pts for f in container.decode(stream) if f.pts is not None], dtype=np.int64))


def _packets_with_pts(path) -> tuple[int, int]:
    """(packets that have a timestamp and a size, how many of them are flagged discard)."""
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        packets = [p for p in container.demux(stream) if p.pts is not None and p.size > 0]
    return len(packets), sum(1 for p in packets if p.is_discard)


def _meta(take: int = 1) -> dict:
    return {"participant_id": "P03", "session_id": "S01", "take_id": f"S01-P03-T{take:02d}", "camera_id": "camA"}


@pytest.mark.parametrize("fixture", TRIMMED)
def test_t_io_20_the_trimmed_fixtures_really_have_discarded_packets(request, fixture):
    path = request.getfixturevalue(fixture)
    n_packets, n_discard = _packets_with_pts(path)
    assert n_discard >= 1, "the fixture has no edit list: the test below would prove nothing"
    assert n_packets - n_discard == len(_decoded_pts(path))


@pytest.mark.parametrize("fixture", EVERY_VIDEO)
def test_t_io_20_the_packet_scan_equals_the_decoded_frames(request, fixture):
    path = request.getfixturevalue(fixture)
    scan = scan_pts_ticks(path)
    decoded = _decoded_pts(path)
    assert scan.pts.size == decoded.size
    assert np.array_equal(scan.pts, decoded)
    assert scan.t_sec.min() >= 0, "a frame before the stream start is a packet the decoder drops"


@pytest.mark.parametrize("fixture", TRIMMED)
def test_t_io_21_ingest_of_a_trimmed_clip_stores_the_decoded_frames_only(request, fixture, ingest_settings):
    path = request.getfixturevalue(fixture)
    n_decoded = _decoded_pts(path).size
    result = ingest_recording(path, _meta(), ingest_settings)
    rec_dir = ingest_settings.data_dir / "recordings" / result.manifest.recording_id

    assert result.manifest.n_frames == n_decoded
    t_sec = pq.read_table(rec_dir / "pts.parquet")["t_sec"].to_numpy()
    assert t_sec.size == n_decoded
    assert t_sec[0] == 0.0 and t_sec.min() >= 0


@pytest.mark.parametrize("fixture", TRIMMED)
def test_t_io_22_the_proxy_of_a_trimmed_clip_passes_the_check(request, fixture, ingest_settings):
    path = request.getfixturevalue(fixture)
    n_decoded = _decoded_pts(path).size
    result = ingest_recording(path, _meta(), ingest_settings)
    rec_dir = ingest_settings.data_dir / "recordings" / result.manifest.recording_id

    manifest = make_proxy(rec_dir)

    assert manifest.n_frames_source == manifest.n_frames_proxy == n_decoded
    assert manifest.check.passed is True
    assert manifest.check.max_abs_dt_frames <= 1.0
