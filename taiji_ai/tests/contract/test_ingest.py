"""T-IO-06..09 and T-IO-12..18: ``ingest_recording`` (P2.02).

An ingest copies one phone video into ``data/recordings/<recording_id>/``, keeps its real timestamps in
``pts.parquet``, writes ``recording.json`` last and then one row in the ``recording`` table. Nothing half-done may be
left behind, the original is never changed, and a recording needs a participant with analysis consent. No message and
no log line holds the source path or file name (AGENTS.md section 6).
"""

from __future__ import annotations

import dataclasses
import logging
import math
import os
import shutil
import sqlite3
import stat
from contextlib import closing
from datetime import datetime, timedelta
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pyarrow.parquet as pq
import pytest

from taiji_ai.config import Settings
from taiji_ai.io import ingest as ingest_module
from taiji_ai.io.frames import VFR_RULE, PtsScan, scan_pts_ticks
from taiji_ai.io.ingest import (
    AlreadyIngested,
    ConsentMissing,
    IngestError,
    IngestMeta,
    MetaInvalid,
    NoVideoStream,
    SourceTooLarge,
    SourceUnreadable,
    ingest_recording,
)
from taiji_ai.io.probe import probe_video
from taiji_ai.schemas._base import read_manifest
from taiji_ai.schemas.recording import RecordingManifest
from taiji_ai.store.artifacts import sha256_file
from taiji_ai.store.db import connect

META = {"participant_id": "P03", "session_id": "S01", "take_id": "S01-P03-T02", "camera_id": "camA"}
NAME_WITH_A_PERSON = "Tập luyện 24 thức - Nguyễn Văn A.mp4"


def _copy(src: Path, tmp_path: Path, name: str = "clip.mp4") -> Path:
    folder = tmp_path / "phone"
    folder.mkdir(exist_ok=True)
    dst = folder / name
    shutil.copyfile(src, dst)
    return dst


def _rows(settings: Settings, table: str) -> list[sqlite3.Row]:
    with closing(connect(settings.db_path, settings.migrations_dir)) as conn:
        return conn.execute(f"SELECT * FROM {table}").fetchall()


def _folders(settings: Settings) -> list[str]:
    root = settings.data_dir / "recordings"
    return sorted(p.name for p in root.iterdir()) if root.exists() else []


def _nothing_ingested(settings: Settings) -> None:
    assert _rows(settings, "recording") == []
    assert _folders(settings) == []  # not even a staging or an orphan folder


# --- T-IO-09: manifest, row and pts file ----------------------------------------------------------------------------


def test_t_io_09_a_constant_frame_rate_video_is_stored_with_manifest_row_and_pts(ingest_settings, cfr_video, tmp_path):
    src = _copy(cfr_video, tmp_path)
    before = datetime.now().astimezone() - timedelta(seconds=1)
    result = ingest_recording(src, META, ingest_settings)
    m = result.manifest
    assert result.created is True

    rec_dir = ingest_settings.data_dir / "recordings" / m.recording_id
    assert sorted(p.name for p in rec_dir.iterdir()) == ["pts.parquet", "recording.json", "source.mp4"]
    assert read_manifest(rec_dir / "recording.json", RecordingManifest) == m

    assert (m.participant_id, m.session_id, m.take_id, m.camera_id) == ("P03", "S01", "S01-P03-T02", "camA")
    assert m.consent_ref == "CONSENT-2026-011"  # copied from the participant row
    assert m.sha256 == sha256_file(src) and m.size_bytes == src.stat().st_size and m.source_ext == ".mp4"
    assert (m.width, m.height, m.display_rotation) == (320, 240, 0)
    assert m.codec == "h264" and "mp4" in m.container
    assert m.time_base == "1/15360" and m.start_pts == 0 and m.n_frames == 60
    assert m.pts_span_s == pytest.approx(59 / 30) and m.median_dt_s == pytest.approx(1 / 30)
    assert m.measured_fps == pytest.approx(30.0, rel=1e-6) and m.dt_rel_std == pytest.approx(0.0, abs=1e-9)
    assert m.nominal_fps == pytest.approx(30.0, abs=0.01) and m.r_frame_rate == pytest.approx(30.0, abs=0.01)
    assert m.n_duplicate_pts == 0 and m.vfr is False
    assert m.vfr_rule.model_dump() == dataclasses.asdict(VFR_RULE)  # the rule that decided, with all its numbers
    assert m.audio is not None and m.audio.codec == "aac" and abs(m.audio.start_offset_s) < 0.1
    assert m.capture is None
    assert before <= m.ingested_at <= datetime.now().astimezone() + timedelta(seconds=1)
    assert m.tools.pyav == av.__version__ and m.tools.taiji_ai
    assert m.tools.ffprobe != "unknown" and m.tools.ffprobe[0].isdigit()  # "9.0.1-essentials_build-www.gyan.dev"

    [row] = _rows(ingest_settings, "recording")
    assert dict(row) == m.to_db_row()
    assert row["source_path"] == f"recordings/{m.recording_id}/source.mp4"

    table = pq.read_table(rec_dir / "pts.parquet")
    scan = scan_pts_ticks(src)
    assert table.schema.names == ["frame_index", "pts", "t_sec"]
    assert np.array_equal(table["pts"].to_numpy(), scan.pts)
    assert np.array_equal(table["frame_index"].to_numpy(), np.arange(60))
    assert np.allclose(table["t_sec"].to_numpy(), scan.t_sec)
    assert table.schema.metadata[b"time_base"] == b"1/15360" and table.schema.metadata[b"start_pts"] == b"0"


def test_t_io_09_a_variable_frame_rate_video_without_audio_is_flagged(ingest_settings, vfr_video, tmp_path):
    m = ingest_recording(_copy(vfr_video, tmp_path), META, ingest_settings).manifest
    assert m.vfr is True and m.audio is None and m.n_frames == 40
    assert m.dt_rel_std is not None and m.dt_rel_std > 0.1
    [row] = _rows(ingest_settings, "recording")
    assert (row["vfr"], row["has_audio"]) == (1, 0)


def test_t_io_09_the_display_rotation_is_stored_and_the_coded_size_kept(ingest_settings, rotated_video, tmp_path):
    m = ingest_recording(_copy(rotated_video, tmp_path), META, ingest_settings).manifest
    assert (m.display_rotation, m.width, m.height) == (90, 320, 240)
    assert _rows(ingest_settings, "recording")[0]["rotation"] == 90


def test_t_io_09_a_video_that_does_not_start_at_zero_keeps_its_start_pts_and_the_audio_offset(
    ingest_settings, offset_video, tmp_path
):
    src = _copy(offset_video, tmp_path)
    m = ingest_recording(src, META, ingest_settings).manifest
    assert scan_pts_ticks(src).start_pts == 76800  # 5.0 s at 1/15360: the fixture really starts late
    assert m.start_pts == 76800 and m.pts_span_s == pytest.approx(59 / 30)
    table = pq.read_table(ingest_settings.data_dir / "recordings" / m.recording_id / "pts.parquet")
    assert table["pts"][0].as_py() == 76800  # the stored pts are the raw ones
    assert table["t_sec"][0].as_py() == 0.0  # t_sec counts from the start of the video stream
    assert table.schema.metadata[b"start_pts"] == b"76800"
    assert m.audio is not None
    assert 0.3 < m.audio.start_offset_s < 0.7  # relative to the video start (5.0 s), not the absolute 5.5 s


def test_t_io_09_a_one_frame_video_has_no_interval_and_nothing_is_made_up(ingest_settings, one_frame_video, tmp_path):
    src = _copy(one_frame_video, tmp_path)
    result = ingest_recording(src, META, ingest_settings)
    m = result.manifest
    assert m.n_frames == 1 and m.pts_span_s == 0.0 and m.vfr is False and m.n_duplicate_pts == 0
    assert (m.median_dt_s, m.measured_fps, m.dt_rel_std) == (None, None, None)  # one frame has no interval, not a 0
    table = pq.read_table(ingest_settings.data_dir / "recordings" / m.recording_id / "pts.parquet")
    assert table.num_rows == 1 and table["t_sec"][0].as_py() == 0.0
    [row] = _rows(ingest_settings, "recording")
    assert row["duration_s"] is None or row["duration_s"] > 0  # the container value, or unknown: never an invented 0


def test_t_io_09_duplicate_timestamps_are_counted_and_no_frame_is_dropped(
    ingest_settings, cfr_video, tmp_path, monkeypatch
):
    real = scan_pts_ticks(cfr_video)
    pts = real.pts.copy()
    pts[10] = pts[9]  # the 11th frame carries the timestamp of the 10th
    monkeypatch.setattr(ingest_module, "scan_pts_ticks", lambda path: PtsScan(pts, real.time_base, real.start_pts))
    m = ingest_recording(_copy(cfr_video, tmp_path), META, ingest_settings).manifest
    assert m.n_frames == 60 and m.n_duplicate_pts == 1
    table = pq.read_table(ingest_settings.data_dir / "recordings" / m.recording_id / "pts.parquet")
    assert table.num_rows == 60


def test_t_io_09_the_container_frame_rates_are_stored_as_the_container_gives_them(
    ingest_settings, cfr_video, tmp_path, monkeypatch
):
    real = ingest_module.probe_video
    monkeypatch.setattr(
        ingest_module,
        "probe_video",
        lambda p: real(p).model_copy(update={"avg_frame_rate": 24.0, "r_frame_rate": 30.0}),
    )
    m = ingest_recording(_copy(cfr_video, tmp_path), META, ingest_settings).manifest
    assert (m.nominal_fps, m.r_frame_rate) == (24.0, 30.0)


def test_t_io_09_an_upper_case_extension_is_accepted_and_stored_in_lower_case(ingest_settings, cfr_video, tmp_path):
    result = ingest_recording(_copy(cfr_video, tmp_path, "CLIP.MP4"), META, ingest_settings)
    assert result.manifest.source_ext == ".mp4"
    folder = ingest_settings.data_dir / "recordings" / result.manifest.recording_id
    assert sorted(p.name for p in folder.iterdir()) == ["pts.parquet", "recording.json", "source.mp4"]


def test_t_io_09_capture_info_is_stored_when_given(ingest_settings, cfr_video, tmp_path):
    meta = {**META, "capture": {"camera_role": "main_axis", "height_m": 1.1, "distance_m": 4.5, "fps_setting": 30.0}}
    m = ingest_recording(_copy(cfr_video, tmp_path), meta, ingest_settings).manifest
    assert m.capture is not None and (m.capture.camera_role, m.capture.height_m) == ("main_axis", 1.1)


def test_t_io_09_an_ingest_meta_object_is_accepted_as_well_as_a_mapping(ingest_settings, cfr_video, tmp_path):
    result = ingest_recording(_copy(cfr_video, tmp_path), IngestMeta.model_validate(META), ingest_settings)
    assert result.created is True


# --- T-IO-12: BUG-0046 through the whole ingest ----------------------------------------------------------------------


@pytest.mark.parametrize("fixture", ["coarse_cfr_30", "coarse_cfr_2997"])
def test_t_io_12_a_constant_frame_rate_video_with_a_coarse_time_base_is_stored_as_not_vfr(
    request, ingest_settings, tmp_path, fixture
):
    src = _copy(request.getfixturevalue(fixture), tmp_path)
    m = ingest_recording(src, META, ingest_settings).manifest
    assert m.time_base == "1/1000" and m.vfr is False
    assert _rows(ingest_settings, "recording")[0]["vfr"] == 0
    assert m.dt_rel_std is not None and 0.01 < m.dt_rel_std < 0.02  # the 1.4 % spread of BUG-0046, kept as measured


# --- T-IO-06: the original is untouched, the copy is read-only -------------------------------------------------------


def test_t_io_06_the_original_is_unchanged_and_the_stored_copy_is_identical_and_read_only(
    ingest_settings, cfr_video, tmp_path
):
    src = _copy(cfr_video, tmp_path)
    st0 = src.stat()
    sha0 = sha256_file(src)
    m = ingest_recording(src, META, ingest_settings).manifest
    st1 = src.stat()
    assert (st1.st_size, st1.st_mtime_ns) == (st0.st_size, st0.st_mtime_ns) and sha256_file(src) == sha0
    assert os.access(src, os.W_OK)  # we did not touch its attributes
    stored = ingest_settings.data_dir / "recordings" / m.recording_id / "source.mp4"
    assert sha256_file(stored) == sha0 == m.sha256
    assert not os.access(stored, os.W_OK) and not (stored.stat().st_mode & stat.S_IWRITE)


# --- T-IO-07: the same file twice ------------------------------------------------------------------------------------


def test_t_io_07_the_same_file_twice_gives_the_same_record_and_stores_nothing_more(
    ingest_settings, cfr_video, tmp_path
):
    src = _copy(cfr_video, tmp_path)
    first = ingest_recording(src, META, ingest_settings)
    second = ingest_recording(src, META, ingest_settings)
    assert first.created is True and second.created is False
    assert second.manifest == first.manifest
    assert len(_rows(ingest_settings, "recording")) == 1 and _folders(ingest_settings) == [first.manifest.recording_id]
    other_name = ingest_recording(_copy(cfr_video, tmp_path, "same-bytes.mp4"), META, ingest_settings)
    assert other_name.created is False and other_name.manifest == first.manifest  # the hash decides, not the name


def test_t_io_07b_the_same_file_under_other_ids_is_refused(ingest_settings, cfr_video, tmp_path):
    src = _copy(cfr_video, tmp_path)
    ingest_recording(src, META, ingest_settings)
    for other in ({"take_id": "S01-P03-T03"}, {"camera_id": "camB"}):
        with pytest.raises(AlreadyIngested, match="already ingested"):
            ingest_recording(src, {**META, **other}, ingest_settings)
    assert len(_rows(ingest_settings, "recording")) == 1 and len(_folders(ingest_settings)) == 1


# --- T-IO-17: a take and camera that already have a recording --------------------------------------------------------


def test_t_io_17_a_second_file_for_the_same_take_and_camera_is_refused(ingest_settings, cfr_video, vfr_video, tmp_path):
    first = ingest_recording(_copy(cfr_video, tmp_path), META, ingest_settings).manifest
    with pytest.raises(AlreadyIngested, match="already has a recording"):
        ingest_recording(_copy(vfr_video, tmp_path, "retake.mp4"), META, ingest_settings)
    assert [r["recording_id"] for r in _rows(ingest_settings, "recording")] == [first.recording_id]
    assert _folders(ingest_settings) == [first.recording_id]
    other_camera = ingest_recording(_copy(vfr_video, tmp_path, "b.mp4"), {**META, "camera_id": "camB"}, ingest_settings)
    assert other_camera.created is True  # the second camera of the same take is exactly what is allowed


# --- T-IO-08: unreadable sources leave nothing behind ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "error", "message"),
    [
        ("truncated_video", SourceUnreadable, "could not read"),
        ("empty_video", SourceUnreadable, "empty"),
        ("audio_only_video", NoVideoStream, "no video stream"),
    ],
)
def test_t_io_08_an_unreadable_source_is_refused_clearly_and_leaves_nothing(
    request, ingest_settings, tmp_path, fixture, error, message
):
    src = _copy(request.getfixturevalue(fixture), tmp_path, NAME_WITH_A_PERSON)
    with pytest.raises(error, match=message):
        ingest_recording(src, META, ingest_settings)
    _nothing_ingested(ingest_settings)


def test_t_io_08_an_unsupported_extension_a_folder_and_a_missing_file_are_refused(ingest_settings, cfr_video, tmp_path):
    avi = _copy(cfr_video, tmp_path, "clip.avi")
    folder = tmp_path / "phone" / "dir.mp4"
    folder.mkdir()
    cases = [(avi, "unsupported"), (folder, "regular file"), (tmp_path / "phone" / "absent.mp4", "cannot be read")]
    for src, message in cases:
        with pytest.raises(SourceUnreadable, match=message) as exc:
            ingest_recording(src, META, ingest_settings)
        assert str(tmp_path) not in str(exc.value) and src.name not in str(exc.value)  # no path, no file name
    _nothing_ingested(ingest_settings)


def test_t_io_08_a_pyav_failure_is_refused_with_our_message_not_its_own(
    ingest_settings, cfr_video, tmp_path, monkeypatch
):
    def boom(path):  # PyAV puts the path into its messages
        raise av.error.InvalidDataError(1094995529, "Invalid data found when processing input", str(path))

    monkeypatch.setattr(ingest_module, "scan_pts_ticks", boom)
    with pytest.raises(SourceUnreadable, match="PyAV could not read") as exc:
        ingest_recording(_copy(cfr_video, tmp_path), META, ingest_settings)
    assert str(tmp_path) not in str(exc.value) and "clip" not in str(exc.value)
    _nothing_ingested(ingest_settings)


@pytest.mark.parametrize(
    ("pts", "message"),
    [
        ([], "no frames"),
        ([0, 0, 0, 10], "not increasing"),  # most intervals are 0: the median interval is 0
    ],
    ids=["no-frames", "zero-median-interval"],
)
def test_t_io_08_timestamps_that_cannot_describe_a_video_are_refused(
    ingest_settings, cfr_video, tmp_path, monkeypatch, pts, message
):
    scan = PtsScan(np.asarray(pts, dtype=np.int64), Fraction(1, 1000), 0)
    monkeypatch.setattr(ingest_module, "scan_pts_ticks", lambda path: scan)
    with pytest.raises(SourceUnreadable, match=message):
        ingest_recording(_copy(cfr_video, tmp_path), META, ingest_settings)
    _nothing_ingested(ingest_settings)


# --- T-IO-13: consent -----------------------------------------------------------------------------------------------


def test_t_io_13_a_participant_that_is_not_registered_is_refused(ingest_settings, cfr_video, tmp_path):
    meta = {**META, "participant_id": "P04", "take_id": "S01-P04-T01"}
    with pytest.raises(ConsentMissing, match="participant P04 is not registered"):
        ingest_recording(_copy(cfr_video, tmp_path), meta, ingest_settings)
    _nothing_ingested(ingest_settings)


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("UPDATE participant SET consent_analysis = 0", "no analysis consent"),
        ("UPDATE participant SET consent_ref = ''", "no valid consent reference"),
        ("UPDATE participant SET consent_ref = 'signed on paper'", "no valid consent reference"),
    ],
    ids=["analysis-0", "empty-ref", "free-text-ref"],
)
def test_t_io_13_a_row_written_by_hand_without_valid_consent_is_refused(
    ingest_settings, cfr_video, tmp_path, sql, message
):
    with closing(connect(ingest_settings.db_path, ingest_settings.migrations_dir)) as conn, conn:
        conn.execute(sql)  # the database itself accepts all of these
    with pytest.raises(ConsentMissing, match=message):
        ingest_recording(_copy(cfr_video, tmp_path), META, ingest_settings)
    _nothing_ingested(ingest_settings)


# --- T-IO-14: the meta ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("meta", "field"),
    [
        ({**META, "take_id": "S01-P09-T02"}, "take_id"),  # not the take of this participant
        ({**META, "camera_id": "camera"}, "camera_id"),
        ({**META, "file_name": "x.mp4"}, "file_name"),  # no free text
        ({"participant_id": "P03"}, "session_id"),
        ({**META, "capture": {"camera_role": "ceiling"}}, "camera_role"),
    ],
    ids=["take", "camera", "extra-key", "missing", "role"],
)
def test_t_io_14_a_meta_that_does_not_validate_is_refused_and_nothing_is_written(
    ingest_settings, cfr_video, tmp_path, meta, field
):
    with pytest.raises(MetaInvalid, match=field):
        ingest_recording(_copy(cfr_video, tmp_path), meta, ingest_settings)
    _nothing_ingested(ingest_settings)


def test_t_io_14_a_meta_of_the_wrong_kind_is_refused(ingest_settings, cfr_video, tmp_path):
    with pytest.raises(MetaInvalid):
        ingest_recording(_copy(cfr_video, tmp_path), "P03", ingest_settings)  # type: ignore[arg-type]


# --- T-IO-15: no path and no file name anywhere ----------------------------------------------------------------------


def test_t_io_15_messages_and_log_lines_never_hold_the_source_path_or_file_name(
    ingest_settings, cfr_video, truncated_video, audio_only_video, empty_video, tmp_path, caplog
):
    good = _copy(cfr_video, tmp_path, NAME_WITH_A_PERSON)
    texts: list[str] = []
    with caplog.at_level(logging.DEBUG):
        ingest_recording(good, META, ingest_settings)
        ingest_recording(good, META, ingest_settings)  # already ingested
        for i, bad in enumerate((truncated_video, audio_only_video, empty_video)):
            with pytest.raises(IngestError) as exc:
                ingest_recording(_copy(bad, tmp_path, f"Nguyễn {i}.mp4"), META, ingest_settings)
            texts.append(str(exc.value))
        with pytest.raises(IngestError) as exc:
            ingest_recording(tmp_path / "phone" / "Tập vắng mặt.mp4", META, ingest_settings)
        texts.append(str(exc.value))
        with pytest.raises(AlreadyIngested) as dup:
            ingest_recording(good, {**META, "take_id": "S01-P03-T09"}, ingest_settings)
        texts.append(str(dup.value))
    text = caplog.text + "\n".join(texts)
    for fragment in ("Nguy", "Tập", "luyện", "vắng", str(tmp_path), "phone", ".mp4", "clip"):
        assert fragment not in text, fragment
    assert caplog.text  # the success was logged, with IDs
    assert "P03" in caplog.text or "S01-P03-T02" in caplog.text


# --- T-IO-16: failures leave nothing half-done ----------------------------------------------------------------------


def test_t_io_16_a_failure_after_the_copy_leaves_no_row_and_no_folder(
    ingest_settings, cfr_video, tmp_path, monkeypatch
):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(ingest_module, "write_manifest", boom)
    with pytest.raises(IngestError, match="could not write"):
        ingest_recording(_copy(cfr_video, tmp_path), META, ingest_settings)
    _nothing_ingested(ingest_settings)


def test_t_io_16_any_other_failure_is_not_hidden_and_also_cleans_up(ingest_settings, cfr_video, tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(ingest_module, "atomic_write_parquet", boom)
    with pytest.raises(RuntimeError, match="unexpected"):
        ingest_recording(_copy(cfr_video, tmp_path), META, ingest_settings)
    _nothing_ingested(ingest_settings)


def test_t_io_16_a_failing_row_insert_leaves_only_an_orphan_folder_and_no_row(
    ingest_settings, cfr_video, tmp_path, monkeypatch
):
    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(ingest_module, "insert_recording", boom)
    with pytest.raises(IngestError, match="could not be stored"):
        ingest_recording(_copy(cfr_video, tmp_path), META, ingest_settings)
    assert _rows(ingest_settings, "recording") == []
    [orphan] = _folders(ingest_settings)
    assert orphan.startswith(".orphan-")  # a folder without a row is the only possible leftover
    files = sorted(p.name for p in (ingest_settings.data_dir / "recordings" / orphan).iterdir())
    assert files == ["pts.parquet", "recording.json", "source.mp4"]  # complete, so a check can decide about it


def test_t_io_16_when_the_orphan_rename_fails_too_the_error_says_to_remove_the_folder(
    ingest_settings, cfr_video, tmp_path, monkeypatch
):
    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    real_replace = os.replace

    def replace(src, dst):
        if ".orphan-" in str(dst):
            raise PermissionError("denied")
        real_replace(src, dst)

    monkeypatch.setattr(ingest_module, "insert_recording", boom)
    monkeypatch.setattr(ingest_module.os, "replace", replace)  # same module object as os: delegates for other targets
    with pytest.raises(IngestError, match="remove the folder by hand"):
        ingest_recording(_copy(cfr_video, tmp_path), META, ingest_settings)
    assert _rows(ingest_settings, "recording") == []
    [leftover] = _folders(ingest_settings)
    assert not leftover.startswith(".")  # still under its final name: the message tells the maintainer what to remove


def test_t_io_16_the_row_is_inserted_only_when_the_folder_is_complete_under_its_final_name(
    ingest_settings, cfr_video, tmp_path, monkeypatch
):
    seen: dict[str, list[str] | None] = {}
    real = ingest_module.insert_recording

    def spy(conn, row):
        folder = ingest_settings.data_dir / "recordings" / row["recording_id"]
        seen["files"] = sorted(p.name for p in folder.iterdir()) if folder.is_dir() else None
        real(conn, row)

    monkeypatch.setattr(ingest_module, "insert_recording", spy)
    ingest_recording(_copy(cfr_video, tmp_path), META, ingest_settings)
    assert seen["files"] == ["pts.parquet", "recording.json", "source.mp4"]  # never a row without its folder


def test_t_io_16_the_manifest_is_written_after_the_copy_and_the_timestamps(
    ingest_settings, cfr_video, tmp_path, monkeypatch
):
    seen: dict[str, list[str]] = {}
    real = ingest_module.write_manifest

    def spy(path, model):
        seen["files"] = sorted(p.name for p in Path(path).parent.iterdir())
        return real(path, model)

    monkeypatch.setattr(ingest_module, "write_manifest", spy)
    ingest_recording(_copy(cfr_video, tmp_path), META, ingest_settings)
    assert seen["files"] == ["pts.parquet", "source.mp4"]  # AGENTS.md 5.8: the manifest is the last file written


def test_t_io_16_a_copy_that_differs_from_the_hash_is_refused(ingest_settings, cfr_video, tmp_path, monkeypatch):
    calls = {"n": 0}
    real = ingest_module.sha256_file

    def changing(path):
        calls["n"] += 1
        return real(path) if calls["n"] == 1 else "0" * 64  # the second hash is the one of the copy

    monkeypatch.setattr(ingest_module, "sha256_file", changing)
    with pytest.raises(IngestError, match="differs from the source"):
        ingest_recording(_copy(cfr_video, tmp_path), META, ingest_settings)
    _nothing_ingested(ingest_settings)


def test_t_io_16_a_read_only_tree_can_be_removed(tmp_path):
    folder = tmp_path / "staging" / "inner"
    folder.mkdir(parents=True)
    victim = folder / "source.mp4"
    victim.write_bytes(b"x")
    os.chmod(victim, stat.S_IREAD)
    ingest_module._remove_tree(tmp_path / "staging")
    assert not (tmp_path / "staging").exists()
    ingest_module._remove_tree(tmp_path / "staging")  # absent: no error


# --- T-IO-18: limits ------------------------------------------------------------------------------------------------


def test_t_io_18_a_file_larger_than_the_limit_is_refused(ingest_settings, cfr_video, tmp_path):
    small = dataclasses.replace(ingest_settings, max_source_bytes=1000)
    with pytest.raises(SourceTooLarge, match="larger than the limit"):
        ingest_recording(_copy(cfr_video, tmp_path), META, small)
    _nothing_ingested(ingest_settings)


def test_t_io_18_a_video_longer_than_the_limit_is_refused_and_one_inside_it_is_not(
    ingest_settings, cfr_video, tmp_path
):
    src = _copy(cfr_video, tmp_path)  # 2 s
    short = dataclasses.replace(ingest_settings, max_source_duration_s=1.9)
    with pytest.raises(SourceTooLarge, match="longer than the limit"):
        ingest_recording(src, META, short)
    _nothing_ingested(ingest_settings)
    roomy = dataclasses.replace(ingest_settings, max_source_duration_s=2.1)
    assert ingest_recording(src, META, roomy).created is True


def test_t_io_18_the_size_limit_is_inclusive(ingest_settings, cfr_video, tmp_path):
    src = _copy(cfr_video, tmp_path)
    size = src.stat().st_size
    with pytest.raises(SourceTooLarge):
        ingest_recording(src, META, dataclasses.replace(ingest_settings, max_source_bytes=size - 1))
    _nothing_ingested(ingest_settings)
    assert ingest_recording(src, META, dataclasses.replace(ingest_settings, max_source_bytes=size)).created is True


def _measured_duration(src: Path) -> float:
    """The duration the limit is applied to (DEC-0028): the larger of the container duration and the last timestamp
    plus one median interval, measured here from the file itself."""
    video, scan = probe_video(src), scan_pts_ticks(src)
    tick = float(scan.time_base)
    span = float(scan.pts[-1] - scan.pts[0]) * tick
    return max(video.duration_s or 0.0, span + float(np.median(np.diff(scan.pts))) * tick)


def test_t_io_18_the_duration_limit_is_inclusive(ingest_settings, cfr_video, tmp_path):
    src = _copy(cfr_video, tmp_path)
    duration = _measured_duration(src)
    just_below = dataclasses.replace(ingest_settings, max_source_duration_s=math.nextafter(duration, 0.0))
    with pytest.raises(SourceTooLarge, match="longer than the limit"):
        ingest_recording(src, META, just_below)
    _nothing_ingested(ingest_settings)
    exact = dataclasses.replace(ingest_settings, max_source_duration_s=duration)
    assert ingest_recording(src, META, exact).created is True


@pytest.mark.parametrize(
    ("container_s", "limit_s"),
    [
        (100.0, 10.0),  # the container says 100 s while the timestamps say 2 s
        (0.5, 1.0),  # the container says 0.5 s while the timestamps say 2 s
        (None, 1.0),  # the container says nothing
    ],
    ids=["container-longer", "timestamps-longer", "no-container-duration"],
)
def test_t_io_18_the_longer_of_the_container_and_the_timestamps_is_what_counts(
    ingest_settings, cfr_video, tmp_path, monkeypatch, container_s, limit_s
):
    real = ingest_module.probe_video
    monkeypatch.setattr(ingest_module, "probe_video", lambda p: real(p).model_copy(update={"duration_s": container_s}))
    settings = dataclasses.replace(ingest_settings, max_source_duration_s=limit_s)
    with pytest.raises(SourceTooLarge, match="longer than the limit"):
        ingest_recording(_copy(cfr_video, tmp_path), META, settings)  # the clip is 2 s
    _nothing_ingested(ingest_settings)
