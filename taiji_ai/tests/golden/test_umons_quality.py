"""T-QLT-12: the quality chain on real, long Kinect sequences of UMONS-TAICHI (D12) (P4.08).

Six files, chosen from the measurements of the analysis (``Docs/tasks/P4.08.md``): the longest sequence, the one in
which a second body is in the picture for a few seconds (the file repeats timestamps), one with a long pause in the
clock, the one with the lowest coverage and the most dropped frames, one with joints at (0, 0, 0), and one in which the
swap flag fires. Each runs through the adapter and ``run_quality_arrays`` with the default parameters.

The files are local and third-party (CC BY-NC-SA 4.0, allowed use ``dev-test``, ``Docs/DATASET_REGISTRY_TAIJI.md``): the
tests are skipped when the folder is absent, store no frame, no value and no golden number, and assert relations and
sanity bounds only (data validity, not thresholds on a movement: AGENTS.md 5.5).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taiji_ai.bench.umons import PROVIDED, UmonsError, find_umons, load_kinect, run_sequence
from taiji_ai.pose.skeleton import JOINTS
from taiji_ai.quality.quality_io import load_quality, save_quality

pytestmark = pytest.mark.dataset

ROOT = Path(__file__).resolve().parents[3] / "datasets" / "taiji" / "umons"
FILES = ("P08T03C01", "P04T02C03", "P02T02C09", "P09T02C02", "P01T02C07", "P07T02C02")
SANITY = 0.85  # a share of usable frames or of usable cells of the joints that Kinect has
PROVIDED_NAMES = {JOINTS[j] for j in PROVIDED}


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
        out[name] = (seq, run_sequence(seq))
    return out


@pytest.mark.parametrize("name", FILES)
def test_t_qlt_12_the_chain_runs_on_a_long_sequence_and_the_coverage_is_reasonable(runs, name):
    seq, result = runs[name]
    assert result.error is None and result.report is not None, result.error
    assert len(seq.t_sec) >= 4000  # the plan: a sequence of 4,000+ frames
    rep = result.report
    seg = rep.intervals[0]
    assert rep.timeline.resampled is True  # no Kinect clock is a straight line: the grid of P4.04 is not the identity
    assert seg.observed + seg.bridged + seg.missing == seg.cells and seg.source_rows == len(seq.t_sec)
    provided = [j for j in seg.joints if j.joint in PROVIDED_NAMES]
    usable = sum(j.observed + j.bridged for j in provided) / (len(provided) * seg.rows)
    assert len(provided) == 17 and usable >= SANITY, usable
    assert seg.usable_frames / seg.rows >= SANITY
    absent = [j for j in seg.joints if j.joint not in PROVIDED_NAMES]  # the nine joints that Kinect does not have
    assert len(absent) == 9 and all(j.observed == 0 and j.bridged == 0 and j.missing == seg.rows for j in absent)


@pytest.mark.parametrize("name", FILES)
def test_t_qlt_12_the_report_of_a_real_sequence_is_a_valid_quality_json(runs, name, tmp_path):
    _, result = runs[name]
    path = tmp_path / "quality.json"
    save_quality(path, result.report)
    assert load_quality(path) == result.report
    assert path.stat().st_size < 100_000


def test_t_qlt_12_two_bodies_in_one_frame_are_not_tracked_and_never_bridged(runs):
    seq, result = runs["P04T02C03"]
    assert seq.ambiguous_timestamps > 0 and seq.repeated_rows >= seq.ambiguous_timestamps
    assert (~seq.tracked).sum() >= seq.ambiguous_timestamps
    seg = result.report.intervals[0]
    # the rows are the last of the file, so their gaps are open at the end; whatever the place, the 17 joints of each
    # row stay NaN with the reason not_tracked in the final layer, none of them is bridged
    assert seg.missing_by_reason.not_tracked >= 17 * seq.ambiguous_timestamps


def test_t_qlt_12_a_pause_in_the_clock_is_no_frame_and_dropped_frames_are_counted(runs):
    _, pause = runs["P02T02C09"]
    assert pause.steps_pause > 0 and pause.report.intervals[0].missing_by_reason.no_frame > 0
    _, dropped = runs["P09T02C02"]
    assert dropped.steps_long > 100


def test_t_qlt_12_joints_at_zero_are_low_conf_and_the_swap_flag_sees_a_swap(runs):
    seq, result = runs["P01T02C07"]
    assert seq.zero_joint_cells > 0
    assert result.report.intervals[0].unobserved_by_reason.low_conf >= seq.zero_joint_cells
    _, swap = runs["P07T02C02"]
    assert any(w.startswith("lr_swap_suspect@") for w in swap.report.warnings)


def test_t_qlt_12_the_longest_sequence_has_more_than_ten_thousand_rows_and_nothing_breaks(runs):
    seq, result = runs["P08T03C01"]
    assert len(seq.t_sec) > 10_000 and result.report.timeline.grid_rows > len(seq.t_sec)
    assert result.seconds < 60  # a sanity bound on speed (the analysis took about 5 s)
