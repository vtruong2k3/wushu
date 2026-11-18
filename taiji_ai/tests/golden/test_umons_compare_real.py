"""The comparison chain on real UMONS-TAICHI files: segmented pairs, the labels, one pair of recordings (P6.07).

The files are local and third-party (D12, CC BY-NC-SA 4.0, allowed use ``dev-test`` and ``benchmark``,
``Docs/DATASET_REGISTRY_TAIJI.md``): the tests are skipped when they are absent, store no frame, no value and no golden
number, and assert relations only (the files read, the ids and the counts the dataset notes give, a path that exists and
is monotone, matched times inside the query's span, IoU in [0, 1], finite errors): AGENTS.md 5.5 forbids a threshold on
a movement that no signed record gave, and these files are out of domain (9.4.4). The numbers of the runs are in
``Docs/reports/p6_umons_check.md`` (M-CMP-01), made by ``tools/umons_compare.py``.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from taiji_ai.bench.umons import UmonsError, find_umons, load_kinect
from taiji_ai.bench.umons_compare import (
    N_UNITS,
    SegmentId,
    candidate_pairs,
    features_loader,
    features_of,
    find_folder,
    label_parts,
    list_labels,
    list_segments,
    list_sequences,
    load_labels,
    load_segment,
    make_settings,
    run_boundaries,
    transfer_parts,
)
from taiji_ai.compare.align import align

pytestmark = pytest.mark.dataset

UMONS = Path(__file__).resolve().parents[3] / "datasets" / "taiji" / "umons"
SEGMENTS = 1815  # the files of Segmented_Kinect (datasets/taiji/README.md)
LABELS = 131  # the files of Labels
MAX_ROWS = 6000  # the smallest pair of recordings is about 4,500 by 3,300 rows (a few seconds); a larger one is skipped


@pytest.fixture(scope="module")
def dataset() -> Path:
    if not (UMONS / "extracted" / "Segmented_Kinect").is_dir():
        pytest.skip("UMONS-TAICHI is not downloaded (datasets/taiji/umons/extracted)")
    return UMONS


@pytest.fixture(scope="module")
def segments(dataset: Path) -> dict[SegmentId, Path]:
    return list_segments(find_folder(dataset, "Segmented_Kinect"))


@pytest.fixture(scope="module")
def labels(dataset: Path):
    return {q: load_labels(path) for q, path in list_labels(find_folder(dataset, "Labels")).items()}


def test_the_folders_hold_the_files_the_dataset_notes_give(dataset: Path, segments, labels):
    assert len(segments) == SEGMENTS and len(labels) == LABELS
    assert all(s.klass >= 1 and s.side >= 1 and s.repetition >= 1 for s in segments)
    try:
        sequences = list_sequences(find_umons(dataset))
    except UmonsError as exc:
        pytest.fail(f"the Kinect folder is not the registered dataset: {exc}")
    assert set(labels) >= set(sequences)  # every Kinect recording has a label file


def test_every_label_file_parses_and_has_a_part_to_measure(labels):
    for q, rows in labels.items():
        times = [r.t_sec for r in rows]
        assert times == sorted(set(times)), q.text  # strictly increasing: the reader refuses anything else
        parts = label_parts(rows)
        assert any(p.family != "rest" and p.end_s is not None for p in parts), q.text


def pick(segments: dict[SegmentId, Path]):
    """A reference, a query of the same class and side from another performer, and a query of another class on that
    side, all of a similar length (the first such triple in id order; a choice by the ids, not by any value)."""
    lengths: dict[SegmentId, int] = {}

    def rows(s: SegmentId) -> int:
        if s not in lengths:
            lengths[s] = len(load_segment(segments[s]).t_sec)
        return lengths[s]

    for reference in segments:
        if reference.side != 1:
            continue
        same = next(
            (
                s
                for s in segments
                if (s.klass, s.side) == (reference.klass, reference.side)
                and s.performer != reference.performer
                and 0.8 <= rows(s) / rows(reference) <= 1.25
            ),
            None,
        )
        other = next(
            (
                s
                for s in segments
                if s.klass != reference.klass
                and s.side == reference.side
                and s.performer != reference.performer
                and 0.8 <= rows(s) / rows(reference) <= 1.25
            ),
            None,
        )
        if same is not None and other is not None:
            return reference, same, other
    pytest.skip("no triple of similar lengths found")


def test_a_real_triple_of_segments_aligns_with_a_monotone_path_and_matched_times_in_the_query(segments):
    reference, same, other = pick(segments)
    settings = make_settings(band=0.2)
    ref_f = features_of(load_segment(segments[reference]))
    assert len(ref_f.units) == N_UNITS and ref_f.valid.any()
    for query in (same, other):
        query_f = features_of(load_segment(segments[query]))
        alignment = align(ref_f, query_f, min_visible=settings.min_visible, band=settings.band, step=settings.step)
        assert alignment.result.status == "ok", (reference.text, query.text)
        assert alignment.distance is not None and math.isfinite(alignment.distance) and alignment.distance >= 0.0
        path = alignment.result.path
        assert tuple(path[0]) == (0, 0) and tuple(path[-1]) == (len(query_f.t_sec) - 1, len(ref_f.t_sec) - 1)
        assert (np.diff(path, axis=0) >= 0).all()
        matched = alignment.matched_query_times()
        assert np.isfinite(matched).all() and (np.diff(matched) >= 0.0).all()
        assert matched[0] >= query_f.t_sec[0] and matched[-1] <= query_f.t_sec[-1]
        assert alignment.settings["min_visible"] == settings.min_visible and alignment.settings["band"] == 0.2


def test_the_smallest_real_pair_of_recordings_carries_its_boundaries(dataset: Path, labels):
    sequences = list_sequences(find_umons(dataset))
    usable = candidate_pairs(labels, set(sequences)).usable
    assert usable, "no two performers of one capture have equal label sequences"
    rows = {q: len(load_kinect(sequences[q]).t_sec) for pair in usable for q in pair}
    reference, query = min(usable, key=lambda pair: rows[pair[0]] * rows[pair[1]])
    if max(rows[reference], rows[query]) > MAX_ROWS:
        pytest.skip("the smallest pair of recordings is longer than the limit of this test")
    loader = features_loader({q.text: sequences[q] for q in (reference, query)}, load_kinect)
    run = run_boundaries([(reference, query)], labels, loader, make_settings(band=0.1))
    assert run.failed_sequences == () and run.failed_pairs == () and len(run.pairs) == 1
    (pair,) = run.pairs
    assert pair.status in ("ok", "no_path")
    if pair.status == "ok":
        assert pair.parts, "an aligned pair of two labelled performances has parts to compare"
        for part in pair.parts:
            assert 0.0 <= part.iou <= 1.0 and 0.0 <= part.uniform_iou <= 1.0
            assert all(
                math.isfinite(x)
                for x in (part.start_error_s, part.end_error_s, part.uniform_start_error_s, part.uniform_end_error_s)
            )
        assert pair.parts_open + pair.parts_outside + len(pair.parts) >= 1
        alignment = align(loader(reference.text), loader(query.text), min_visible=11, band=0.1, step="symmetricP1")
        again = transfer_parts(alignment, labels[reference], labels[query], reference, query)
        assert [(p.rank, p.iou) for p in again.parts] == [(p.rank, p.iou) for p in pair.parts]  # deterministic
