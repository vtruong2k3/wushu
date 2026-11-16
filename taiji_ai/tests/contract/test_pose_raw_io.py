"""T-POSE-08a..i: save and load of ``pose_raw.npz`` (schema ``pose_raw/1``) (P3.03)."""

from __future__ import annotations

import dataclasses
import json
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pytest

from helpers.fake_pose import ScriptedPose, standing_person
from helpers.pose_raw_build import RECORDING_ID, make_pose_raw
from taiji_ai.config import Settings
from taiji_ai.io.ingest import ingest_recording
from taiji_ai.pose.raw_io import PoseRawError, load_pose_raw, save_pose_raw
from taiji_ai.pose.runner import PoseRunParams, run_pose
from taiji_ai.store import artifacts
from taiji_ai.store.artifacts import sha256_file

EXPECTED_ARRAYS = {
    "schema_version", "meta_json", "frame_index", "t_sec", "person_offsets", "bboxes", "keypoints", "scores",
    "from_detector",
}  # fmt: skip
DATA_ARRAYS = ("frame_index", "t_sec", "person_offsets", "bboxes", "keypoints", "scores", "from_detector")


def _arrays(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def _rewrite(path: Path, **changes: np.ndarray | None) -> None:
    """Change the archive behind the writer's back (a damaged or foreign file); ``None`` removes an array."""
    arrays = _arrays(path)
    for name, value in changes.items():
        if value is None:
            arrays.pop(name)
        else:
            arrays[name] = value
    np.savez_compressed(path, **arrays)


def _rewrite_meta(path: Path, change) -> None:
    meta = json.loads(str(_arrays(path)["meta_json"]))
    change(meta)
    _rewrite(path, meta_json=np.array(json.dumps(meta)))


@pytest.fixture
def saved(tmp_path: Path) -> Path:
    path = tmp_path / "pose_raw.npz"
    save_pose_raw(path, make_pose_raw())
    return path


# --- T-POSE-08a, 08b: the round trip -----------------------------------------------------------------------------


@pytest.mark.parametrize("empty", [False, True], ids=["persons", "nobody_in_any_frame"])
def test_t_pose_08a_a_saved_pose_comes_back_identical(tmp_path: Path, empty: bool):
    raw = make_pose_raw(empty=empty)
    path = tmp_path / "pose_raw.npz"
    save_pose_raw(path, raw)

    loaded = load_pose_raw(path)

    assert raw.equals(raw)  # a pose with a NaN score is equal to itself
    assert loaded.equals(raw)
    for name in DATA_ARRAYS:
        a, b = getattr(raw, name), getattr(loaded, name)
        assert a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes(), (
            name
        )  # bit-identical, NaN included
    assert loaded.params == raw.params and loaded.segment_s == raw.segment_s and loaded.image_size == raw.image_size
    assert loaded.model_fingerprint == raw.model_fingerprint and loaded.providers == raw.providers
    assert (loaded.stats.n_frames, loaded.stats.n_detector_calls, loaded.stats.n_pose_calls) == (6, 4, 5)
    assert loaded.stats.n_persons_total == int(raw.person_offsets[-1])
    assert loaded.stats.elapsed_s is None  # the wall clock is not kept in the file and is not invented
    if not empty:
        assert np.isnan(loaded.scores[1, 3]) and tuple(loaded.keypoints[0, 0]) == (
            -25.0,
            400.0,
        )  # nothing clamped or filled


def test_t_pose_08a_the_archive_holds_the_documented_arrays_and_nothing_else(saved: Path):
    assert set(_arrays(saved)) == EXPECTED_ARRAYS
    assert str(_arrays(saved)["schema_version"]) == "pose_raw/1"


def test_t_pose_08b_save_returns_the_sha256_of_the_file_on_disk(tmp_path: Path):
    path = tmp_path / "pose_raw.npz"

    digest = save_pose_raw(path, make_pose_raw())

    assert len(digest) == 64 and digest == sha256_file(path)


# --- T-POSE-08c: refusals on load --------------------------------------------------------------------------------


def _bad_arrays() -> list:
    raw = make_pose_raw()
    f, d = raw.n_frames, int(raw.person_offsets[-1])
    off = raw.person_offsets
    cases = []
    for name in DATA_ARRAYS + ("meta_json", "schema_version"):
        cases.append(pytest.param({name: None}, name, id=f"missing_{name}"))
    cases += [
        pytest.param({"extra": np.zeros(1)}, "extra", id="extra_array"),
        pytest.param({"keypoints": raw.keypoints.astype(np.float64)}, "keypoints", id="keypoints_float64"),
        pytest.param({"frame_index": raw.frame_index.astype(np.int64)}, "frame_index", id="frame_index_int64"),
        pytest.param({"person_offsets": off.astype(np.int32)}, "person_offsets", id="offsets_int32"),
        pytest.param({"from_detector": raw.from_detector.astype(np.uint8)}, "from_detector", id="from_detector_uint8"),
        pytest.param({"t_sec": raw.t_sec.astype(np.float32)}, "t_sec", id="t_sec_float32"),
        pytest.param({"keypoints": raw.keypoints[:, :25]}, "keypoints", id="keypoints_25_joints"),
        pytest.param({"scores": raw.scores[:, :25]}, "scores", id="scores_25_joints"),
        pytest.param({"bboxes": raw.bboxes[:, :3]}, "bboxes", id="bboxes_3_columns"),
        pytest.param({"t_sec": raw.t_sec[: f - 1]}, "t_sec", id="t_sec_one_short"),
        pytest.param({"person_offsets": off[:f]}, "person_offsets", id="offsets_one_short"),
        pytest.param({"person_offsets": off + 1}, "person_offsets", id="offsets_do_not_start_at_zero"),
        pytest.param(
            {"person_offsets": np.where(np.arange(f + 1) == 3, 0, off)}, "person_offsets", id="offsets_decrease"
        ),
        pytest.param(
            {"person_offsets": np.append(off[:-1], d + 1)}, "person_offsets", id="offsets_end_beyond_the_rows"
        ),
        pytest.param(
            {"t_sec": np.where(np.arange(f) == 2, raw.t_sec[1], raw.t_sec)}, "t_sec", id="t_sec_not_increasing"
        ),
        pytest.param({"t_sec": np.where(np.arange(f) == 2, np.nan, raw.t_sec)}, "t_sec", id="t_sec_nan"),
        pytest.param({"frame_index": raw.frame_index[::-1].copy()}, "frame_index", id="frame_index_decreasing"),
        pytest.param(
            {"frame_index": np.where(np.arange(f) == 0, -1, raw.frame_index).astype(np.int32)},
            "frame_index",
            id="frame_index_negative",
        ),
    ]
    return cases


@pytest.mark.parametrize(("changes", "field"), _bad_arrays())
def test_t_pose_08c_a_damaged_or_inconsistent_archive_is_refused_naming_the_field(
    saved: Path, changes: dict, field: str
):
    _rewrite(saved, **changes)

    with pytest.raises(PoseRawError, match=field):
        load_pose_raw(saved)


@pytest.mark.parametrize(
    ("change", "field"),
    [
        (lambda m: m["counts"].update(n_frames=7), "n_frames"),
        (lambda m: m["counts"].update(n_persons_total=99), "n_persons_total"),
    ],
    ids=["header_frames_disagree", "header_persons_disagree"],
)
def test_t_pose_08c_header_counts_must_agree_with_the_arrays(saved: Path, change, field: str):
    _rewrite_meta(saved, change)

    with pytest.raises(PoseRawError, match=field):
        load_pose_raw(saved)


# --- T-POSE-08d: refusals of the header --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "field"),
    [
        (lambda m: m.update(schema_version="pose_raw/2"), "schema_version"),
        (lambda m: m.update(skeleton="halpe26/2"), "skeleton"),
        (lambda m: m.update(recording_id="nope"), "recording_id"),
        (lambda m: m.update(segment_s=[0.9, 0.5]), "segment_s"),
        (lambda m: m.update(image_size=[0, 1080]), "image_size"),
        (lambda m: m.update(unknown=1), "unknown"),
        (lambda m: m.update(model_fingerprint={}), "model_fingerprint"),
        (lambda m: m.pop("providers"), "providers"),
    ],
    ids=[
        "version_in_json",
        "skeleton",
        "recording_id",
        "segment",
        "image_size",
        "unknown_field",
        "no_fingerprint",
        "no_providers",
    ],
)
def test_t_pose_08d_a_bad_header_is_refused_naming_the_field(saved: Path, change, field: str):
    _rewrite_meta(saved, change)

    with pytest.raises(PoseRawError, match=field):
        load_pose_raw(saved)


def test_t_pose_08d_another_version_is_refused_naming_both_versions(saved: Path):
    _rewrite(saved, schema_version=np.array("pose_raw/2"))

    with pytest.raises(PoseRawError) as info:
        load_pose_raw(saved)

    assert "pose_raw/2" in str(info.value) and "pose_raw/1" in str(info.value)


# --- T-POSE-08e: files that are not an archive of ours -----------------------------------------------------------


def test_t_pose_08e_files_that_are_not_a_pose_archive_are_refused(tmp_path: Path, saved: Path):
    good = saved.read_bytes()
    cases = {
        "random": np.random.default_rng(1).bytes(4096),
        "empty": b"",
        "text": b"this is not an archive\n",
        "truncated": good[: len(good) // 2],
    }
    for name, content in cases.items():
        path = tmp_path / f"{name}.npz"
        path.write_bytes(content)
        with pytest.raises(PoseRawError) as info:
            load_pose_raw(path)
        assert info.value.__cause__ is not None, name


def test_t_pose_08e_an_archive_with_a_pickled_array_is_refused(tmp_path: Path):
    raw = make_pose_raw()
    path = tmp_path / "pickled.npz"
    arrays = {n: getattr(raw, n) for n in DATA_ARRAYS}
    np.savez(path, **arrays, schema_version=np.array("pose_raw/1"), meta_json=np.array([{"a": 1}], dtype=object))

    with pytest.raises(PoseRawError):
        load_pose_raw(path)


def test_t_pose_08e_a_missing_file_is_refused(tmp_path: Path):
    with pytest.raises(PoseRawError):
        load_pose_raw(tmp_path / "nope.npz")


# --- T-POSE-08f: the write is atomic -----------------------------------------------------------------------------


def test_t_pose_08f_a_failing_replace_keeps_the_previous_file_and_leaves_no_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "pose_raw.npz"
    old = make_pose_raw(seed=1)
    save_pose_raw(path, old)

    def broken_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(artifacts.os, "replace", broken_replace)
    with pytest.raises(PoseRawError, match="could not write"):
        save_pose_raw(path, make_pose_raw(seed=2))
    monkeypatch.undo()

    assert load_pose_raw(path).equals(old)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pose_raw.npz"]


def test_t_pose_08f_a_second_save_replaces_the_first_completely(tmp_path: Path):
    path = tmp_path / "pose_raw.npz"
    save_pose_raw(path, make_pose_raw(seed=1))
    new = make_pose_raw(empty=True)
    save_pose_raw(path, new)

    assert load_pose_raw(path).equals(new)


def test_t_pose_08f_a_missing_folder_is_refused_and_not_created(tmp_path: Path):
    with pytest.raises(PoseRawError, match="folder"):
        save_pose_raw(tmp_path / "no_such_folder" / "pose_raw.npz", make_pose_raw())

    assert not (tmp_path / "no_such_folder").exists()


# --- T-POSE-08g: a pose that breaks the rules cannot be saved ----------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        lambda r: dataclasses.replace(r, keypoints=r.keypoints.astype(np.float64)),
        lambda r: dataclasses.replace(r, person_offsets=np.append(r.person_offsets[:-1], 99)),
        lambda r: dataclasses.replace(r, frame_index=r.frame_index[::-1].copy()),
        lambda r: dataclasses.replace(r, stats=dataclasses.replace(r.stats, n_persons_total=99)),
        lambda r: dataclasses.replace(r, stats=dataclasses.replace(r.stats, n_frames=2)),
        lambda r: dataclasses.replace(r, model_fingerprint={}),
        lambda r: dataclasses.replace(r, segment_s=(1.0, 0.5)),
    ],
    ids=["dtype", "offsets", "frame_index_order", "persons_count", "frames_count", "no_fingerprint", "segment"],
)
def test_t_pose_08g_a_pose_that_breaks_the_rules_is_not_written(tmp_path: Path, change):
    path = tmp_path / "pose_raw.npz"

    with pytest.raises(PoseRawError):
        save_pose_raw(path, change(make_pose_raw()))

    assert list(tmp_path.iterdir()) == []


# --- T-POSE-08h: no path and no file name in the file ------------------------------------------------------------


def test_t_pose_08h_the_file_holds_no_path_and_no_file_name(tmp_path: Path, saved: Path):
    with zipfile.ZipFile(saved) as z:
        assert {n.removesuffix(".npy") for n in z.namelist()} == EXPECTED_ARRAYS
    text = str(_arrays(saved)["meta_json"])
    meta = json.loads(text)

    assert meta["recording_id"] == RECORDING_ID
    for forbidden in (str(tmp_path), "\\", ".mp4", ".mov", ".mkv", "source", "recordings"):
        assert forbidden not in text, forbidden


# --- T-POSE-08i: the real path -----------------------------------------------------------------------------------


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")
def test_t_pose_08i_a_run_saved_and_loaded_is_the_same_run(cfr_video: Path, ingest_settings: Settings, tmp_path: Path):
    meta = {"participant_id": "P03", "session_id": "S01", "take_id": "S01-P03-T01", "camera_id": "camA"}
    rec = ingest_recording(cfr_video, meta, ingest_settings)
    rec_dir = ingest_settings.data_dir / "recordings" / rec.manifest.recording_id
    model = ScriptedPose(lambda pos: [standing_person(), standing_person(cx=250.0, valid=3)], by_pixel=False)

    raw = run_pose(rec_dir, 0.2, 0.8, model, params=PoseRunParams(segment_margin_s=0.1))
    path = tmp_path / "pose_raw.npz"
    save_pose_raw(path, raw)
    loaded = load_pose_raw(path)

    # the weak second person is stored on the detector frames only (it is not followed in between)
    assert loaded.equals(raw) and raw.n_frames > 5
    assert int(raw.person_offsets[-1]) == raw.n_frames + raw.stats.n_detector_calls
    assert loaded.recording_id == rec.manifest.recording_id
    assert loaded.stats.n_detector_calls == raw.stats.n_detector_calls and loaded.stats.elapsed_s is None


def test_t_pose_08c_offsets_that_are_one_short_but_end_at_the_row_count_are_refused(saved: Path):
    """Only the length of ``person_offsets`` is wrong: the arrays hold exactly as many rows as its last value says."""
    arrays = _arrays(saved)
    off = arrays["person_offsets"]
    short = off[: off.size - 1]
    rows = int(short[-1])
    _rewrite(
        saved,
        person_offsets=short,
        bboxes=arrays["bboxes"][:rows],
        keypoints=arrays["keypoints"][:rows],
        scores=arrays["scores"][:rows],
        from_detector=arrays["from_detector"][:rows],
    )

    with pytest.raises(PoseRawError, match="person_offsets"):
        load_pose_raw(saved)


def test_t_pose_08c_offsets_that_do_not_start_at_zero_but_fit_the_rows_are_refused(saved: Path):
    """Only the start of ``person_offsets`` is wrong: shifted by one, with one more row in every person array."""
    arrays = _arrays(saved)
    more = {
        name: np.concatenate([arrays[name], arrays[name][:1]])
        for name in ("bboxes", "keypoints", "scores", "from_detector")
    }
    _rewrite(saved, person_offsets=arrays["person_offsets"] + 1, **more)

    with pytest.raises(PoseRawError, match="person_offsets must start at 0"):
        load_pose_raw(saved)
