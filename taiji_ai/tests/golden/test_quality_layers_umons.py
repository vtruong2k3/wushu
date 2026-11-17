"""T-QLT-13h (real data): the two layer files of long, real, non-uniform Kinect sequences of UMONS-TAICHI (D12) (X.29).

Two files from the choice of ``test_umons_quality.py``: the longest sequence (11,790 rows) and one with a pause of 733
ms in its clock. Each runs through ``run_quality_arrays`` with the default parameters, is saved as ``pose_masked.npz``
and ``pose_filtered.npz`` and read back; the way back from the file must be the way back of the chain, bit for bit.

The files are local and third-party (CC BY-NC-SA 4.0, allowed use ``dev-test``, ``Docs/DATASET_REGISTRY_TAIJI.md``):
the tests are skipped when the folder is absent, write only to ``tmp_path``, store no value and assert relations only.
A layer made from them is non-commercial (AGENTS.md 9.4.6): the header says so through ``data_sources``.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from taiji_ai.bench.umons import UmonsError, find_umons, load_kinect
from taiji_ai.quality.chain import run_quality_arrays
from taiji_ai.quality.layers_io import (
    load_pose_filtered,
    load_pose_masked,
    pose_filtered_from_result,
    pose_masked_from_result,
    save_pose_filtered,
    save_pose_masked,
)
from taiji_ai.schemas.quality_layers import DataSource

pytestmark = pytest.mark.dataset

ROOT = Path(__file__).resolve().parents[3] / "datasets" / "taiji" / "umons"
FILES = ("P08T03C01", "P02T02C09")
RECORDING_ID = "5d7c1b9e-2f4a-4c6d-8e3b-1a9f0c2d4e6f"
SOURCES = (DataSource(dataset_id="D12", license="CC BY-NC-SA 4.0"),)
MAX_BYTES = 12_000_000  # a sanity bound on the size of one layer file of 11,790 rows


@pytest.fixture(scope="module")
def folder() -> Path:
    if not (ROOT / "extracted" / "Kinect").is_dir():
        pytest.skip("UMONS-TAICHI is not downloaded (datasets/taiji/umons/extracted/Kinect)")
    try:
        return find_umons(ROOT)
    except UmonsError as exc:  # present but not the dataset we registered: say so, do not skip
        pytest.fail(f"the UMONS folder is not the registered dataset: {exc}")


@pytest.fixture(scope="module")
def runs(folder: Path):
    out = {}
    for name in FILES:
        seq = load_kinect(folder / f"{name}.txt")
        out[name] = (seq, run_quality_arrays(seq.keypoints, seq.scores, seq.t_sec, tracked=seq.tracked))
    return out


@pytest.mark.parametrize("name", FILES)
def test_t_qlt_13h_a_real_sequence_saved_and_loaded_gives_the_same_layers_and_the_same_way_back(
    runs, tmp_path: Path, name: str
):
    seq, result = runs[name]
    frame_index = np.arange(len(seq.t_sec), dtype=np.int64)
    masked = pose_masked_from_result(result, recording_id=RECORDING_ID, frame_index=frame_index, data_sources=SOURCES)
    filtered = pose_filtered_from_result(
        result, recording_id=RECORDING_ID, frame_index=frame_index, data_sources=SOURCES
    )
    started = time.perf_counter()
    save_pose_masked(tmp_path / "pose_masked.npz", masked)
    save_pose_filtered(tmp_path / "pose_filtered.npz", filtered)
    back_masked = load_pose_masked(tmp_path / "pose_masked.npz")
    back_filtered = load_pose_filtered(tmp_path / "pose_filtered.npz")
    assert time.perf_counter() - started < 30.0  # a sanity bound on speed
    assert back_masked.equals(masked) and back_filtered.equals(filtered)
    assert back_filtered.meta.timeline.resampled is True and len(back_filtered.t_grid) > len(back_filtered.t_sec)
    expected = result.filtered_on_source()
    got = back_filtered.on_source()
    assert got.dtype == expected.dtype and np.array_equal(got, expected, equal_nan=True)
    assert back_filtered.outside.sum() <= 2  # at most the first and the last row are off the lattice
    assert (tmp_path / "pose_masked.npz").stat().st_size < MAX_BYTES
    assert (tmp_path / "pose_filtered.npz").stat().st_size < MAX_BYTES
    assert back_masked.meta.data_sources == SOURCES and back_filtered.meta.data_sources == SOURCES


def test_t_qlt_13h_a_real_pause_is_no_frame_in_the_file_and_never_bridged(runs, tmp_path: Path):
    seq, result = runs["P02T02C09"]
    filtered = pose_filtered_from_result(
        result, recording_id=RECORDING_ID, frame_index=np.arange(len(seq.t_sec)), data_sources=SOURCES
    )
    save_pose_filtered(tmp_path / "pose_filtered.npz", filtered)
    loaded = load_pose_filtered(tmp_path / "pose_filtered.npz")
    no_frame = loaded.reason == 6
    assert no_frame.any() and np.isnan(loaded.keypoints[no_frame]).all() and not loaded.interpolated[no_frame].any()
