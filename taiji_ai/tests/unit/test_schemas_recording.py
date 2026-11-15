"""T-SCH-01 (recording part): ``RecordingManifest``, ``IngestMeta``, ``CaptureInfo`` and ``ProxyManifest`` (P2.01).

The manifests are the data contracts of Phase 2: what ``recording.json`` and ``proxy.json`` may contain. Unknown
values are ``null``, never 0 or an invented number (AGENTS.md section 5.1); nothing can hold a person's name, an
original file name or an absolute path (section 5.9); a manifest is always valid JSON (no NaN or infinity).
"""

from __future__ import annotations

import copy
import json
from pathlib import PurePosixPath, PureWindowsPath

import pytest
from pydantic import ValidationError

from taiji_ai.config import PROJECT_ROOT
from taiji_ai.schemas._base import ManifestError, parse_manifest, read_manifest, write_manifest
from taiji_ai.schemas.recording import CaptureInfo, IngestMeta, ProxyManifest, RecordingManifest
from taiji_ai.store.db import connect

REC_ID = "3f2b8c1e-5d4a-4e7b-9c1a-0b2d3e4f5a6b"  # a UUID4: version nibble 4, variant nibble 9
SHA = "a" * 64


def _recording() -> dict:
    return {
        "schema_version": "recording/1",
        "recording_id": REC_ID,
        "sha256": SHA,
        "participant_id": "P03",
        "session_id": "S01",
        "take_id": "S01-P03-T02",
        "camera_id": "camA",
        "consent_ref": "CONSENT-2026-011",
        "source_ext": ".mp4",
        "size_bytes": 812345678,
        "container": "mov,mp4,m4a,3gp,3g2,mj2",
        "codec": "h264",
        "width": 1920,
        "height": 1080,
        "display_rotation": 0,
        "time_base": "1/90000",
        "start_pts": 0,
        "n_frames": 11172,
        "pts_span_s": 372.4,
        "duration_s": 372.43,
        "nominal_fps": 30.0,
        "r_frame_rate": 30.0,
        "measured_fps": 30.0,
        "median_dt_s": 1 / 30,
        "dt_rel_std": 0.0,
        "n_duplicate_pts": 0,
        "vfr": False,
        "vfr_rule": {"name": "tick_median", "version": 1, "rel_tol": 0.01, "tick_tol": 1, "max_share": 0.01},
        "audio": {"codec": "aac", "sample_rate": 48000, "channels": 2, "start_offset_s": 0.0},
        "capture": {"camera_role": "main_axis", "height_m": 1.1, "distance_m": 4.5, "fps_setting": 30.0},
        "ingested_at": "2026-11-20T09:12:00+07:00",
        "tools": {"ffprobe": "9.0.1", "pyav": "19.0.2", "taiji_ai": "0.1.0"},
    }


def _proxy() -> dict:
    return {
        "schema_version": "proxy/1",
        "recording_id": REC_ID,
        "source_sha256": SHA,
        "proxy_sha256": "b" * 64,
        "height": 720,
        "rotation_applied": 90,
        "ffmpeg": "9.0.1",
        "args": ["-map", "0:v:0", "-vf", "scale=-2:'min(720,ih)'", "-c:v", "libx264", "-crf", "23"],
        "n_frames_source": 11172,
        "n_frames_proxy": 11172,
        "check": {"points": 10, "max_abs_dt_s": 0.0, "max_abs_dt_frames": 0.0, "passed": True},
    }


def _set(d: dict, path: str, value) -> dict:
    d = copy.deepcopy(d)
    cur = d
    *head, last = path.split(".")
    for key in head:
        cur = cur[key]
    cur[last] = value
    return d


def _del(d: dict, path: str) -> dict:
    d = copy.deepcopy(d)
    cur = d
    *head, last = path.split(".")
    for key in head:
        cur = cur[key]
    del cur[last]
    return d


# --- T-SCH-01a: round trip -----------------------------------------------------------------------------------------


def test_t_sch_01a_recording_manifest_round_trips_through_a_file(tmp_path):
    m = parse_manifest(RecordingManifest, _recording())
    path = write_manifest(tmp_path / "rec" / "recording.json", m)
    assert read_manifest(path, RecordingManifest) == m
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == "recording/1"
    assert not list(path.parent.glob("*.tmp"))  # atomic write leaves no temporary file


def test_t_sch_01a_unknown_values_are_null_and_round_trip_as_null(tmp_path):
    d = _recording()
    for key in ("audio", "capture", "duration_s", "nominal_fps", "r_frame_rate"):
        d[key] = None
    m = parse_manifest(RecordingManifest, d)
    data = json.loads(write_manifest(tmp_path / "recording.json", m).read_text(encoding="utf-8"))
    assert data["audio"] is None and data["capture"] is None and data["duration_s"] is None
    assert read_manifest(tmp_path / "recording.json", RecordingManifest) == m


def test_t_sch_01a_manifests_are_immutable():
    m = parse_manifest(RecordingManifest, _recording())
    with pytest.raises(ValidationError, match="frozen"):
        m.width = 1  # type: ignore[misc]
    p = parse_manifest(ProxyManifest, _proxy())
    with pytest.raises(ValidationError, match="frozen"):
        p.height = 1  # type: ignore[misc]


def test_t_sch_01a_proxy_manifest_round_trips(tmp_path):
    m = parse_manifest(ProxyManifest, _proxy())
    assert read_manifest(write_manifest(tmp_path / "proxy.json", m), ProxyManifest) == m


# --- T-SCH-01b: structure -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mutated", "field"),
    [
        (_del(_recording(), "sha256"), "sha256"),
        (_del(_recording(), "tools"), "tools"),
        (_del(_recording(), "vfr_rule.rel_tol"), "rel_tol"),
        (_set(_recording(), "width", "wide"), "width"),
        (_set(_recording(), "width", True), "width"),  # a boolean is not a size
        (_set(_recording(), "width", "1920"), "width"),  # a string is not a size
        (_set(_recording(), "vfr", "maybe"), "vfr"),
        (_set(_recording(), "vfr", "true"), "vfr"),  # strict: only a real boolean
        (_set(_recording(), "vfr", 1), "vfr"),
        (_set(_recording(), "original_name", "IMG_0001.MOV"), "original_name"),
        (_set(_recording(), "audio.surprise", 1), "surprise"),
        (_set(_recording(), "schema_version", "recording/2"), "schema_version"),
        (_set(_recording(), "pts_span_s", float("nan")), "pts_span_s"),
        (_set(_recording(), "dt_rel_std", float("inf")), "dt_rel_std"),
    ],
    ids=[
        "missing-sha",
        "missing-tools",
        "missing-nested",
        "wrong-type-int",
        "bool-as-int",
        "string-as-int",
        "wrong-type-bool",
        "string-as-bool",
        "int-as-bool",
        "extra-original-name",
        "extra-nested",
        "wrong-schema-version",
        "nan",
        "infinity",
    ],
)
def test_t_sch_01b_invalid_manifest_is_rejected_naming_the_field(mutated, field):
    with pytest.raises(ManifestError, match=field):
        parse_manifest(RecordingManifest, mutated)


def test_t_sch_01b_file_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_manifest(tmp_path / "absent.json", RecordingManifest)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ManifestError, match="JSON"):
        read_manifest(bad, RecordingManifest)
    bad.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ManifestError, match="object"):
        read_manifest(bad, RecordingManifest)
    bad.write_bytes(b"\xff\xfe")
    with pytest.raises(ManifestError, match="UTF-8"):
        read_manifest(bad, RecordingManifest)


# --- T-SCH-01c: identifiers, rotation, one frame ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("participant_id", "p03"),
        ("participant_id", "P3"),
        ("participant_id", "P03x"),
        ("session_id", "s01"),
        ("session_id", "S1"),
        ("camera_id", "camera"),
        ("camera_id", "cama"),
        ("camera_id", "camAB"),
        ("consent_ref", "CONSENT-26-011"),
        ("consent_ref", "consent-2026-011"),
        ("consent_ref", "CONSENT-2026-11"),
        ("sha256", "A" * 64),
        ("sha256", "a" * 63),
        ("recording_id", "not-a-uuid"),
        ("recording_id", "3f2b8c1e-5d4a-1e7b-9c1a-0b2d3e4f5a6b"),  # version 1, not 4
        ("take_id", "S02-P03-T02"),  # another session
        ("take_id", "S01-P04-T02"),  # another participant
        ("take_id", "S01-P03-X02"),
        ("take_id", "S01-P03-T2"),
        ("display_rotation", 45),
        ("display_rotation", 360),
        ("display_rotation", -90),
        ("time_base", "90000"),
        ("time_base", "1/0"),
        ("source_ext", "mp4"),
        ("source_ext", ".mp4/../x"),
        ("source_ext", "clip.mp4"),
    ],
)
def test_t_sch_01c_bad_identifier_or_value_is_rejected(path, value):
    with pytest.raises(ManifestError):
        parse_manifest(RecordingManifest, _set(_recording(), path, value))


def test_t_sch_01c_longer_numbers_are_valid():
    d = _set(_recording(), "participant_id", "P100")
    d = _set(d, "session_id", "S10")
    d = _set(d, "take_id", "S10-P100-T12")
    d = _set(d, "camera_id", "camB")
    assert parse_manifest(RecordingManifest, d).take_id == "S10-P100-T12"


def test_t_sch_01c_one_frame_has_no_interval_and_no_spread():
    one = _recording()
    one.update(n_frames=1, pts_span_s=0.0, duration_s=None, median_dt_s=None, measured_fps=None, dt_rel_std=None)
    assert parse_manifest(RecordingManifest, one).n_frames == 1
    for key, value in (("median_dt_s", 0.0333), ("measured_fps", 30.0), ("dt_rel_std", 0.0), ("pts_span_s", 1.0)):
        with pytest.raises(ManifestError):
            parse_manifest(RecordingManifest, _set(one, key, value))
    many = _set(_recording(), "median_dt_s", None)  # two or more frames need a median interval
    with pytest.raises(ManifestError, match="median_dt_s"):
        parse_manifest(RecordingManifest, many)


# --- T-SCH-01d: time zone, no names, relative paths -------------------------------------------------------------------


def test_t_sch_01d_ingested_at_needs_a_time_zone():
    with pytest.raises(ManifestError, match="ingested_at"):
        parse_manifest(RecordingManifest, _set(_recording(), "ingested_at", "2026-11-20T09:12:00"))
    assert parse_manifest(RecordingManifest, _set(_recording(), "ingested_at", "2026-11-20T02:12:00Z"))


def test_t_sch_01d_no_field_can_carry_a_file_name_or_a_path():
    forbidden = ("path", "file_name", "filename", "original", "name")
    for model in (RecordingManifest, IngestMeta, CaptureInfo, ProxyManifest):
        for field in model.model_fields:
            assert not any(word in field for word in forbidden), f"{model.__name__}.{field}"
    for model, data in ((RecordingManifest, _recording()), (ProxyManifest, _proxy())):
        with pytest.raises(ManifestError, match="original_name"):
            parse_manifest(model, _set(data, "original_name", "IMG_0001.MOV"))


def test_t_sch_01d_db_row_source_path_is_relative_and_built_from_the_id():
    row = parse_manifest(RecordingManifest, _recording()).to_db_row()
    assert row["source_path"] == f"recordings/{REC_ID}/source.mp4"
    p = str(row["source_path"])
    assert not PurePosixPath(p).is_absolute() and not PureWindowsPath(p).is_absolute() and ".." not in p.split("/")


# --- T-SCH-01g: the database row ------------------------------------------------------------------------------------


def test_t_sch_01g_db_row_has_exactly_the_columns_of_the_recording_table_and_inserts(tmp_path):
    conn = connect(tmp_path / "app.sqlite3", PROJECT_ROOT / "migrations")
    try:
        columns = [r[1] for r in conn.execute("PRAGMA table_info(recording)")]
        row = parse_manifest(RecordingManifest, _recording()).to_db_row()
        assert set(row) == set(columns)
        conn.execute("INSERT INTO participant(participant_id, consent_ref) VALUES (?, ?)", ("P03", "CONSENT-2026-011"))
        names = ", ".join(row)
        conn.execute(f"INSERT INTO recording({names}) VALUES ({', '.join('?' * len(row))})", list(row.values()))
        got = conn.execute("SELECT * FROM recording").fetchone()
        for key, value in row.items():
            assert got[key] == value, key
        assert (got["vfr"], got["has_audio"], got["rotation"]) == (0, 1, 0)
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"duration_s": 372.43}, 372.43),  # the container value wins
        ({"duration_s": None, "pts_span_s": 372.4, "median_dt_s": 0.04}, 372.44),  # span plus one interval
        (
            {
                "duration_s": None,
                "n_frames": 1,
                "pts_span_s": 0.0,
                "median_dt_s": None,
                "measured_fps": None,
                "dt_rel_std": None,
            },
            None,
        ),  # one frame and no container value: unknown, not 0
    ],
    ids=["container", "span-plus-interval", "unknown"],
)
def test_t_sch_01g_duration_rule(changes, expected):
    d = _recording()
    d.update(changes)
    got = parse_manifest(RecordingManifest, d).to_db_row()["duration_s"]
    assert got == (pytest.approx(expected) if expected is not None else None)


def test_t_sch_01g_flags_map_to_integers():
    d = _set(_recording(), "vfr", True)
    d = _set(d, "audio", None)
    d = _set(d, "display_rotation", 90)
    row = parse_manifest(RecordingManifest, d).to_db_row()
    assert (row["vfr"], row["has_audio"], row["rotation"]) == (1, 0, 90)


# --- T-SCH-01h: proxy -----------------------------------------------------------------------------------------------


def test_t_sch_01h_a_passed_proxy_must_be_within_one_frame_and_have_equal_frame_counts():
    assert parse_manifest(ProxyManifest, _set(_proxy(), "check.max_abs_dt_frames", 1.0))
    with pytest.raises(ManifestError, match="passed"):
        parse_manifest(ProxyManifest, _set(_proxy(), "check.max_abs_dt_frames", 1.01))
    with pytest.raises(ManifestError, match="passed"):
        parse_manifest(ProxyManifest, _set(_proxy(), "n_frames_proxy", 11171))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("schema_version", "proxy/2"),
        ("recording_id", "not-a-uuid"),
        ("source_sha256", "A" * 64),
        ("source_sha256", "a" * 63),
        ("proxy_sha256", "b" * 65),
        ("height", 0),
        ("rotation_applied", 45),
        ("ffmpeg", ""),
        ("n_frames_proxy", 0),
    ],
)
def test_t_sch_01h_bad_identifier_or_value_is_rejected(path, value):
    with pytest.raises(ManifestError, match=path):
        parse_manifest(ProxyManifest, _set(_proxy(), path, value))


def test_t_sch_01h_a_short_clip_is_compared_at_one_point_but_never_at_none():
    assert parse_manifest(ProxyManifest, _set(_proxy(), "check.points", 1))
    with pytest.raises(ManifestError, match="points"):
        parse_manifest(ProxyManifest, _set(_proxy(), "check.points", 0))


def test_t_sch_01h_a_failed_proxy_is_kept_with_its_numbers():
    d = _set(_proxy(), "check.passed", False)
    d = _set(d, "check.max_abs_dt_frames", 5.0)
    d = _set(d, "n_frames_proxy", 11100)
    assert parse_manifest(ProxyManifest, d).check.passed is False


@pytest.mark.parametrize(
    "bad_args",
    [[], ["-i", "C:\\Users\\someone\\clip.mp4"], ["-i", "C:/data/clip.mp4"], ["-i", "/home/someone/clip.mp4"]],
    ids=["empty", "windows-backslash", "windows-slash", "posix"],
)
def test_t_sch_01h_proxy_arguments_are_not_empty_and_hold_no_absolute_path(bad_args):
    with pytest.raises(ManifestError, match="args"):
        parse_manifest(ProxyManifest, _set(_proxy(), "args", bad_args))


# --- T-SCH-01i: the ingest input ------------------------------------------------------------------------------------


def test_t_sch_01i_ingest_meta_and_capture_info():
    meta = IngestMeta.model_validate(
        {
            "participant_id": "P03",
            "session_id": "S01",
            "take_id": "S01-P03-T02",
            "camera_id": "camB",
            "capture": {"camera_role": "side_right", "height_m": 1.0, "distance_m": 4.0, "fps_setting": 30.0},
        }
    )
    assert meta.capture is not None and meta.capture.camera_role == "side_right"
    bare = IngestMeta.model_validate(
        {"participant_id": "P03", "session_id": "S01", "take_id": "S01-P03-T02", "camera_id": "camA"}
    )
    assert bare.capture is None
    assert "consent_ref" not in IngestMeta.model_fields  # the consent reference comes from the participant row


@pytest.mark.parametrize(
    "change",
    [
        {"take_id": "S01-P09-T02"},
        {"camera_id": "camera"},
        {"file_name": "IMG_0001.MOV"},
        {"capture": {"camera_role": "ceiling"}},
        {"capture": {"camera_role": "main_axis", "height_m": 0}},
        {"capture": {"camera_role": "main_axis", "distance_m": -1}},
        {"capture": {"camera_role": "main_axis", "fps_setting": 0}},
        {"capture": {"camera_role": "main_axis", "note": "free text"}},
    ],
    ids=["take", "camera", "file-name", "role", "height", "distance", "fps", "free-text"],
)
def test_t_sch_01i_invalid_ingest_meta_is_rejected(change):
    base = {"participant_id": "P03", "session_id": "S01", "take_id": "S01-P03-T02", "camera_id": "camA"}
    with pytest.raises(ManifestError):
        parse_manifest(IngestMeta, {**base, **change})
