"""T-QLT-13a: the headers of ``pose_masked.npz`` and ``pose_filtered.npz`` (X.29).

A good header is accepted; every bad field is refused and named. Nothing here reads an array: the arrays and the
checks across them are T-QLT-13b to 13h (``tests/contract/test_quality_layers_io.py``).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from helpers.quality_fixtures import clean
from taiji_ai.quality.chain import run_quality_arrays
from taiji_ai.schemas._base import ManifestError, parse_manifest
from taiji_ai.schemas.quality_layers import DataSource, PoseFilteredMeta, PoseMaskedMeta

RECORDING_ID = "0b6f3c1e-5a2d-4f8e-9c3a-7d1e2b4a6c80"


def params_json() -> dict[str, Any]:
    t, kp, score = clean(30)
    return run_quality_arrays(kp, score, t).report.params.model_dump(mode="json")


def masked_header() -> dict[str, Any]:
    params = params_json()
    return {
        "schema_version": "pose_masked/1",
        "skeleton": "halpe26/1",
        "recording_id": RECORDING_ID,
        "mask": params["mask"],
        "swap": params["swap"],
        "counts": {"n_rows": 30},
        "data_sources": [{"dataset_id": "D08", "license": "own recordings"}],
    }


def filtered_header() -> dict[str, Any]:
    return {
        "schema_version": "pose_filtered/1",
        "skeleton": "halpe26/1",
        "recording_id": RECORDING_ID,
        "params": params_json(),
        "timeline": {
            "n_rows": 30, "n_grid_rows": 30, "resampled": False, "step_s": 1 / 30, "sampling_hz": 30.0, "snap_s": 0.0,
        },
        "counts": {"n_mixed_rows": 0, "n_filtered_cells": 780},
        "data_sources": [],
    }  # fmt: skip


def edited(header: dict[str, Any], path: tuple[str | int, ...], value: Any) -> dict[str, Any]:
    out = copy.deepcopy(header)
    node = out
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return out


def removed(header: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
    out = copy.deepcopy(header)
    node = out
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    return out


def test_t_qlt_13a_good_headers_are_accepted():
    masked = parse_manifest(PoseMaskedMeta, masked_header())
    assert masked.counts.n_rows == 30 and masked.data_sources == (
        DataSource(dataset_id="D08", license="own recordings"),
    )
    filtered = parse_manifest(PoseFilteredMeta, filtered_header())
    assert filtered.timeline.n_grid_rows == 30 and filtered.data_sources == ()
    assert filtered.params.hampel.scale_floor_px >= 0.0  # the Hampel floor in pixels, as used


def test_t_qlt_13a_a_header_round_trips_through_json_unchanged():
    for cls, header in ((PoseMaskedMeta, masked_header()), (PoseFilteredMeta, filtered_header())):
        meta = parse_manifest(cls, header)
        assert parse_manifest(cls, meta.model_dump(mode="json")) == meta


MASKED_BAD = [
    (lambda h: edited(h, ("schema_version",), "pose_masked/2"), "schema_version"),
    (lambda h: edited(h, ("schema_version",), "pose_filtered/1"), "schema_version"),
    (lambda h: edited(h, ("skeleton",), "coco17/1"), "skeleton"),
    (lambda h: edited(h, ("recording_id",), "not-a-uuid"), "recording_id"),
    (lambda h: edited(h, ("recording_id",), "0B6F3C1E-5A2D-4F8E-9C3A-7D1E2B4A6C80"), "recording_id"),  # upper case
    (lambda h: edited(h, ("counts", "n_rows"), 0), "n_rows"),
    (lambda h: edited(h, ("counts", "n_rows"), 30.5), "n_rows"),
    (lambda h: edited(h, ("counts", "n_rows"), True), "n_rows"),
    (lambda h: edited(h, ("mask", "tau_kp"), 1.5), "tau_kp"),
    (lambda h: edited(h, ("mask", "essential"), [0, 99]), "essential"),
    (lambda h: edited(h, ("mask", "min_essential_fraction"), 0.0), "min_essential_fraction"),
    (lambda h: edited(h, ("swap", "pairs"), [[1, 40]]), "pairs"),
    (lambda h: edited(h, ("data_sources",), [{"dataset_id": "X08", "license": "own"}]), "dataset_id"),
    (lambda h: edited(h, ("data_sources",), [{"dataset_id": "D8", "license": "own"}]), "dataset_id"),
    (lambda h: edited(h, ("data_sources",), [{"dataset_id": "D08", "license": ""}]), "license"),
    (lambda h: edited(h, ("data_sources",), [{"dataset_id": "D08", "license": "x" * 81}]), "license"),
    (lambda h: edited(h, ("data_sources",), [{"dataset_id": "D08", "license": "line\nbreak"}]), "license"),
    (lambda h: edited(h, ("data_sources",), [{"dataset_id": "D08", "license": "a"}] * 2), "data_sources"),
    (lambda h: edited(h, ("data_sources",), [{"dataset_id": "D08", "license": "a", "path": "C:/x"}]), "path"),
    (lambda h: edited(h, ("data_sources",), None), "data_sources"),
    (lambda h: removed(h, ("data_sources",)), "data_sources"),
    (lambda h: removed(h, ("recording_id",)), "recording_id"),
    (lambda h: removed(h, ("mask",)), "mask"),
    (lambda h: removed(h, ("swap",)), "swap"),
    (lambda h: removed(h, ("counts",)), "counts"),
    (lambda h: {**h, "path": "C:/data/recording.mp4"}, "path"),
    (lambda h: {**h, "participant": "Nguyen"}, "participant"),
]


@pytest.mark.parametrize(("change", "field"), MASKED_BAD)
def test_t_qlt_13a_a_bad_masked_header_is_refused_naming_the_field(change, field: str):
    with pytest.raises(ManifestError, match=field):
        parse_manifest(PoseMaskedMeta, change(masked_header()))


FILTERED_BAD = [
    (lambda h: edited(h, ("schema_version",), "pose_filtered/2"), "schema_version"),
    (lambda h: edited(h, ("skeleton",), "coco17/1"), "skeleton"),
    (lambda h: edited(h, ("recording_id",), "x"), "recording_id"),
    (lambda h: edited(h, ("timeline", "n_rows"), 0), "n_rows"),
    (lambda h: edited(h, ("timeline", "n_grid_rows"), 0), "n_grid_rows"),
    (lambda h: edited(h, ("timeline", "n_grid_rows"), 31), "n_grid_rows"),  # not resampled: the grid is the rows
    (lambda h: edited(h, ("timeline", "resampled"), 1), "resampled"),
    (lambda h: edited(h, ("timeline", "step_s"), -0.01), "step_s"),
    (lambda h: edited(h, ("timeline", "step_s"), None), "step_s"),  # step and rate go together
    (lambda h: edited(h, ("timeline", "sampling_hz"), 25.0), "sampling_hz"),
    (lambda h: edited(h, ("timeline", "snap_s"), -1e-3), "snap_s"),
    (lambda h: edited(h, ("timeline", "snap_s"), float("nan")), "snap_s"),
    (lambda h: edited(h, ("counts", "n_mixed_rows"), 31), "n_mixed_rows"),
    (lambda h: edited(h, ("counts", "n_mixed_rows"), -1), "n_mixed_rows"),
    (lambda h: edited(h, ("counts", "n_filtered_cells"), 781), "n_filtered_cells"),
    (lambda h: edited(h, ("params", "filter", "cutoff_hz"), 0.0), "cutoff_hz"),
    (lambda h: edited(h, ("params", "resample", "max_step_s"), -1.0), "max_step_s"),
    (lambda h: removed(h, ("params", "hampel")), "hampel"),
    (lambda h: removed(h, ("timeline",)), "timeline"),
    (lambda h: removed(h, ("data_sources",)), "data_sources"),
    (lambda h: edited(h, ("data_sources",), [{"dataset_id": "D12", "license": "CC BY-NC-SA 4.0"}] * 2), "data_sources"),
    (lambda h: {**h, "file": "pose.mp4"}, "file"),
]


@pytest.mark.parametrize(("change", "field"), FILTERED_BAD)
def test_t_qlt_13a_a_bad_filtered_header_is_refused_naming_the_field(change, field: str):
    with pytest.raises(ManifestError, match=field):
        parse_manifest(PoseFilteredMeta, change(filtered_header()))


def test_t_qlt_13a_a_resampled_header_may_have_more_grid_rows_than_rows_and_a_single_row_has_no_step():
    resampled = edited(filtered_header(), ("timeline", "resampled"), True)
    resampled = edited(resampled, ("timeline", "n_grid_rows"), 33)
    assert parse_manifest(PoseFilteredMeta, resampled).timeline.n_grid_rows == 33
    one = filtered_header()
    one["timeline"] = {
        "n_rows": 1,
        "n_grid_rows": 1,
        "resampled": False,
        "step_s": None,
        "sampling_hz": None,
        "snap_s": 0.0,
    }
    one["counts"] = {"n_mixed_rows": 0, "n_filtered_cells": 0}
    assert parse_manifest(PoseFilteredMeta, one).timeline.step_s is None


def test_t_qlt_13a_the_licence_of_a_source_is_text_and_the_ids_may_differ():
    header = edited(
        masked_header(),
        ("data_sources",),
        [{"dataset_id": "D08", "license": "own recordings"}, {"dataset_id": "D12", "license": "CC BY-NC-SA 4.0"}],
    )
    meta = parse_manifest(PoseMaskedMeta, header)
    assert [s.dataset_id for s in meta.data_sources] == ["D08", "D12"]
