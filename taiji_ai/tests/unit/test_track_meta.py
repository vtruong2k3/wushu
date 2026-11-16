"""P3.06: the header of ``track.parquet`` (schema ``track/1``, T-TRK-06d)."""

from __future__ import annotations

import copy
import re
from typing import Any

import pytest

from helpers.pose_raw_build import RECORDING_ID
from taiji_ai.schemas._base import ManifestError, parse_manifest
from taiji_ai.schemas.track import TrackMeta


def good() -> dict[str, Any]:
    """A header of 100 frames: one loss (15 lost, 15 target_lost) and one re-attachment, one refusal in between."""
    return {
        "schema_version": "track/1",
        "skeleton": "halpe26/1",
        "recording_id": RECORDING_ID,
        "image_size": [1920, 1080],
        "segment_s": [0.0, 3.3],
        "selection": {
            "method": "user_box", "ambiguous": False, "frame_pos": 0, "frame_index": 100, "t_sec": 0.0, "track_id": 0,
        },
        "params": {"max_lost_s": 0.5, "reattach_cost": 0.5, "max_reattach_s": 5.0, "ambiguity_ratio": 0.6},
        "association": {"w_iou": 1.0, "w_kp": 1.0, "max_cost": 0.3, "max_gap_s": 0.1, "min_common_keypoints": 4},
        "counts": {
            "n_frames": 100, "n_in_segment": 90, "n_tracked": 70, "n_lost": 15, "n_target_lost": 15,
            "n_before_target": 0, "n_reattached": 1, "n_refused": 1, "n_ambiguous": 0,
        },  # fmt: skip
        "needs_reselect": False,
        "reselect_reason": None,
        "events": [
            {"kind": "lost", "frame_pos": 30, "t_sec": 1.0, "track_id": 0, "cost": None, "reason": None},
            {"kind": "target_lost", "frame_pos": 45, "t_sec": 1.5, "track_id": 0, "cost": None, "reason": None},
            {
                "kind": "refused", "frame_pos": 50, "t_sec": 1.6666666666666667, "track_id": 2, "cost": 0.8,
                "reason": "over_threshold",
            },
            {"kind": "reattached", "frame_pos": 60, "t_sec": 2.0, "track_id": 3, "cost": 0.02, "reason": None},
        ],
    }  # fmt: skip


def mutated(*path: str | int, value: Any = ..., delete: bool = False) -> dict[str, Any]:
    data = copy.deepcopy(good())
    node = data
    for key in path[:-1]:
        node = node[key]
    if delete:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return data


def test_t_trk_06d_a_good_header_is_accepted():
    meta = parse_manifest(TrackMeta, good())
    assert meta.schema_version == "track/1" and meta.counts.n_frames == 100
    assert [e.kind for e in meta.events] == ["lost", "target_lost", "refused", "reattached"]
    assert parse_manifest(TrackMeta, meta.model_dump(mode="json")) == meta  # JSON round trip


def test_t_trk_06d_a_header_with_the_reason_to_ask_the_user_is_accepted():
    data = mutated("needs_reselect", value=True)
    data["reselect_reason"] = "reattach_refused"
    assert parse_manifest(TrackMeta, data).reselect_reason == "reattach_refused"


@pytest.mark.parametrize("key", list(good()))
def test_t_trk_06d_a_missing_field_is_refused_and_named(key: str):
    with pytest.raises(ManifestError, match=key):
        parse_manifest(TrackMeta, mutated(key, delete=True))


@pytest.mark.parametrize(
    "path",
    [(), ("selection",), ("params",), ("association",), ("counts",), ("events", 0)],
    ids=["top", "selection", "params", "association", "counts", "event"],
)
def test_t_trk_06d_an_unknown_field_is_refused(path: tuple):
    data = copy.deepcopy(good())
    node = data
    for key in path:
        node = node[key]
    node["surprise"] = 1
    with pytest.raises(ManifestError, match="surprise"):
        parse_manifest(TrackMeta, data)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema_version",), "track/2"),
        (("recording_id",), "not-a-uuid"),
        (("image_size",), [1920, 0]),
        (("image_size",), [1920.5, 1080]),
        (("segment_s",), [3.3, 0.0]),
        (("segment_s",), [0.0, float("nan")]),
        (("selection", "method"), "guess"),
        (("selection", "ambiguous"), "no"),
        (("selection", "frame_pos"), -1),
        (("selection", "track_id"), True),
        (("params", "max_lost_s"), float("nan")),
        (("params", "max_lost_s"), -0.5),
        (("params", "reattach_cost"), 0.0),
        (("params", "reattach_cost"), 1.5),
        (("params", "max_reattach_s"), float("inf")),
        (("params", "max_reattach_s"), 0.2),  # shorter than max_lost_s
        (("selection", "frame_pos"), 100),  # outside the 100 frames
        (("params", "ambiguity_ratio"), 0.0),
        (("association", "max_cost"), 0.0),
        (("association", "min_common_keypoints"), 27),
        (("counts", "n_frames"), "100"),
        (("counts", "n_frames"), 0),
        (("counts", "n_lost"), -1),
        (("counts", "n_in_segment"), 101),
        (("needs_reselect",), "yes"),
        (("reselect_reason",), "because"),
        (("events", 0, "kind"), "vanished"),
        (("events", 0, "frame_pos"), -3),
        (("events", 0, "t_sec"), float("inf")),
        (("events", 2, "reason"), "dislike"),
        (("events", 2, "cost"), float("nan")),
        (("events", 2, "cost"), 1.5),
        (("events", 2, "cost"), -0.1),
    ],
)
def test_t_trk_06d_wrong_values_types_and_ranges_are_refused(path: tuple, value: Any):
    with pytest.raises(ManifestError):
        parse_manifest(TrackMeta, mutated(*path, value=value))


def test_t_trk_06d_the_statuses_must_add_up_to_the_frames():
    data = mutated("counts", "n_tracked", value=71)
    with pytest.raises(ManifestError, match="n_frames"):
        parse_manifest(TrackMeta, data)


def test_t_trk_06d_a_reason_exists_exactly_when_the_user_must_choose_again():
    with pytest.raises(ManifestError, match="reselect_reason"):
        parse_manifest(TrackMeta, mutated("needs_reselect", value=True))  # no reason
    data = mutated("reselect_reason", value="reattach_refused")
    with pytest.raises(ManifestError, match="reselect_reason"):
        parse_manifest(TrackMeta, data)  # a reason although nothing is asked


def test_t_trk_06d_the_counts_of_events_must_agree_with_the_list():
    for key, wrong in (("n_reattached", 2), ("n_refused", 0), ("n_ambiguous", 1)):
        data = copy.deepcopy(good())
        data["counts"][key] = wrong  # the sum of the statuses is unchanged: only the events disagree
        with pytest.raises(ManifestError, match=key):
            parse_manifest(TrackMeta, data)


@pytest.mark.parametrize(
    ("index", "field", "value"),
    [
        (0, "cost", 0.3),  # a loss has no cost
        (0, "reason", "over_threshold"),
        (2, "reason", None),  # a refusal says why
        (2, "cost", None),
        (3, "cost", None),  # a re-attachment has its cost
        (3, "reason", "too_late"),
    ],
)
def test_t_trk_06d_each_kind_of_event_has_its_own_fields(index: int, field: str, value: Any):
    with pytest.raises(ManifestError):
        parse_manifest(TrackMeta, mutated("events", index, field, value=value))


def test_t_trk_06d_an_ambiguous_event_has_a_cost_and_no_reason():
    data = copy.deepcopy(good())
    data["events"][2] = {
        "kind": "ambiguous",
        "frame_pos": 50,
        "t_sec": 1.6666666666666667,
        "track_id": 2,
        "cost": 0.2,
        "reason": None,
    }
    data["counts"]["n_refused"], data["counts"]["n_ambiguous"] = 0, 1
    assert parse_manifest(TrackMeta, data).counts.n_ambiguous == 1
    data["events"][2]["reason"] = "over_threshold"
    with pytest.raises(ManifestError):
        parse_manifest(TrackMeta, data)


def test_t_trk_06d_events_must_not_go_back_in_time():
    data = copy.deepcopy(good())
    data["events"][1], data["events"][0] = data["events"][0], data["events"][1]
    with pytest.raises(ManifestError, match="events"):
        parse_manifest(TrackMeta, data)


def test_t_trk_06d_an_event_must_lie_inside_the_frames():
    with pytest.raises(ManifestError, match="events"):
        parse_manifest(TrackMeta, mutated("events", 3, "frame_pos", value=100))


def test_t_trk_06d_the_header_has_no_path_and_no_file_name():
    text = parse_manifest(TrackMeta, good()).model_dump_json()
    for forbidden in ("\\\\", ".parquet", ".npz", ".mp4", ".mov"):  # an escaped backslash, or a file extension
        assert forbidden not in text
    assert not re.search(
        r'[A-Za-z]:|"/[A-Za-z]', text
    )  # no drive letter, no absolute path (a version like "track/1" is fine)
