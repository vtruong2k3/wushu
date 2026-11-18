"""The cut-off ablation on real recordings: two UMONS Kinect files and one D20 pose chunk (P5.08).

The files are local and third-party (D12, CC BY-NC-SA 4.0, allowed use ``dev-test``; D20, internal use,
``Docs/DATASET_REGISTRY_TAIJI.md``): the tests are skipped when they are absent, store no frame, no value and no golden
number, and assert relations only: the layers of a run have the same grid, reasons, flags and segment at every cut-off,
the measures are finite or ``None`` with a reason, and the tables render (data validity, not thresholds on a movement:
AGENTS.md 5.5). The numbers of the whole datasets are in ``Docs/reports/p5_filter_ablation.md`` (M-MET-01).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from taiji_ai.audit.analyse import target_track
from taiji_ai.bench.filter_ablation import (
    ALL_CUTOFFS,
    NO_FILTER_HZ,
    PAUSE_GRID,
    REFERENCE_HZ,
    aggregate,
    check_invariants,
    layers_at_cutoffs,
    layers_of_track,
    measure_layer,
    render_tables,
)
from taiji_ai.bench.umons import UmonsError, find_umons, load_kinect
from taiji_ai.pose.raw_io import load_pose_raw

pytestmark = pytest.mark.dataset

UMONS = Path(__file__).resolve().parents[3] / "datasets" / "taiji" / "umons"
POSE = Path(__file__).resolve().parents[2] / "data" / "reports" / "p3_08" / "pose"
UMONS_FILES = ("P08T03C01", "P02T02C09")  # the longest sequence and one with a long pause in the clock
RECORDING_ID = "6f1c2a90-3b5d-4e7a-8c14-0d9e5a2b7f31"


@pytest.fixture(scope="module")
def umons_runs():
    if not (UMONS / "extracted" / "Kinect").is_dir():
        pytest.skip("UMONS-TAICHI is not downloaded (datasets/taiji/umons/extracted/Kinect)")
    try:
        folder = find_umons(UMONS)
    except UmonsError as exc:
        pytest.fail(f"the UMONS folder is not the registered dataset: {exc}")
    runs = []
    for name in UMONS_FILES:
        seq = load_kinect(folder / f"{name}.txt")
        layers = layers_at_cutoffs(
            seq.keypoints, seq.scores, seq.t_sec, tracked=seq.tracked, recording_id=RECORDING_ID,
            frame_index=np.arange(len(seq.t_sec), dtype=np.int64),
        )  # fmt: skip
        runs.append(layers)
    return runs


@pytest.fixture(scope="module")
def d20_layers():
    chunk = POSE / "d20-v1_000.npz"
    if not chunk.is_file():
        pytest.skip("the D20 pose chunks of P3.08 are not on this machine (data/reports/p3_08/pose)")
    raw = load_pose_raw(chunk)
    track = target_track(raw)
    assert track is not None, "the performer of the chunk is found by the P3.08 review rule"
    return layers_of_track(track, recording_id=raw.recording_id)


def finite_or_none(value: float | None) -> bool:
    return value is None or math.isfinite(value)


def test_the_layers_of_real_runs_have_the_same_grid_reasons_flags_and_segment_at_every_cutoff(umons_runs, d20_layers):
    for layers in (*umons_runs, d20_layers):
        assert list(layers) == list(ALL_CUTOFFS)
        check_invariants(layers)  # also run when the layers were made: a real run breaks none of them
        assert not layers[NO_FILTER_HZ].filtered.any()
        assert layers[REFERENCE_HZ].filtered.any()  # real runs are long enough to have filtered runs
        assert not np.array_equal(layers[4.0].keypoints, layers[8.0].keypoints, equal_nan=True)


def test_the_measures_of_real_runs_are_finite_or_missing_with_a_reason_and_the_tables_render(umons_runs, d20_layers):
    runs = []
    for layers in (*umons_runs, d20_layers):
        measures = {hz: measure_layer(layer) for hz, layer in layers.items()}
        runs.append(measures)
        for m in measures.values():
            for g in m.groups.values():
                assert g.n_measured > 0 and g.v_p50 is not None and finite_or_none(g.v_p95)
                assert g.v_p50 >= 0.0 and g.v_p95 is not None and g.v_p95 >= g.v_p50
                assert set(g.pauses) == set(PAUSE_GRID)
            assert finite_or_none(m.hip_b.range) and (m.hip_b.range is not None or m.hip_b.reason is not None)
            assert m.hip_a is None
        # the rows with a speed are the rows with a speed at every cut-off: the reasons are the same
        ref = measures[REFERENCE_HZ]
        for m in measures.values():
            for name, g in m.groups.items():
                assert np.array_equal(g.measured, ref.groups[name].measured)
    summary = aggregate(runs)
    text = render_tables({"real smoke": summary})
    assert summary.runs == 3 and "real smoke" in text and "n/a" not in text.split("Hip range")[0].split("Pauses")[0]
    for key, cell in summary.cells.items():
        if key[0] == REFERENCE_HZ:
            assert cell.iou in (None, 1.0) and cell.same_count == 1.0  # the reference agrees with itself
    # a lower cut-off lowers the speed of the hands that a real clip has: the quantiles are ordered
    p95 = [summary.speed[(hz, "hands")].v_p95 for hz in (4.0, 6.0, 8.0, NO_FILTER_HZ)]
    assert all(v is not None for v in p95) and p95 == sorted(p95)  # type: ignore[type-var]
