"""T-AUDIT-07: the pose pass of the failure review: chunks, resumption, joining (P3.08).

A scripted fake model on the synthetic video: no GPU, no model file, no D20.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from helpers.fake_pose import ScriptedPose, standing_person
from taiji_ai.audit import AuditError
from taiji_ai.audit.scan import chunk_frame_mask, chunk_path, load_chunk, plan_chunks, read_pass, run_pose_pass
from taiji_ai.config import Settings
from taiji_ai.io.ingest import ingest_recording

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")

PERSON = standing_person()


def test_t_audit_07_chunks_cover_the_video_and_a_tiny_remainder_joins_the_last_chunk():
    assert plan_chunks(900.0) == [(0.0, 300.0), (300.0, 600.0), (600.0, 900.0)]
    assert plan_chunks(650.0) == [(0.0, 300.0), (300.0, 600.0), (600.0, 650.0)]
    assert plan_chunks(600.5) == [(0.0, 300.0), (300.0, 600.5)]  # 0.5 s left over: joined
    assert plan_chunks(100.0) == [(0.0, 100.0)]
    assert plan_chunks(1.0, 1.0) == [(0.0, 1.0)]
    chunks = plan_chunks(5912.4)
    assert (
        chunks[0][0] == 0.0
        and chunks[-1][1] == 5912.4
        and all(a[1] == b[0] for a, b in zip(chunks, chunks[1:], strict=False))
    )


@pytest.mark.parametrize(
    "bad", [(0.0, 300.0), (-5.0, 300.0), (float("nan"), 300.0), (100.0, 0.0), (100.0, float("inf"))]
)
def test_t_audit_07_bad_durations_and_chunk_lengths_are_refused(bad: tuple[float, float]):
    with pytest.raises(AuditError):
        plan_chunks(*bad)


def test_t_audit_07_a_chunk_is_start_inclusive_end_exclusive_and_the_ends_of_the_video_keep_their_margins():
    t = np.array([-0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5])
    assert chunk_frame_mask(t, 1.0, 2.0, first=False, last=False).tolist() == [0, 0, 0, 1, 1, 0, 0]
    assert chunk_frame_mask(t, 0.0, 1.0, first=True, last=False).tolist() == [1, 1, 1, 0, 0, 0, 0]  # nothing before it
    assert chunk_frame_mask(t, 2.0, 3.0, first=False, last=True).tolist() == [0, 0, 0, 0, 0, 1, 1]  # nothing after it
    assert chunk_frame_mask(t, 0.0, 3.0, first=True, last=True).all()


@pytest.fixture
def recordings(cfr_video: Path, ingest_settings: Settings) -> dict[str, Path]:
    meta = {"participant_id": "P03", "session_id": "S01", "take_id": "S01-P03-T01", "camera_id": "camA"}
    rec = ingest_recording(cfr_video, meta, ingest_settings)
    return {"d20-v9": ingest_settings.data_dir / "recordings" / rec.manifest.recording_id}


def test_t_audit_07_the_pass_writes_one_file_per_chunk_and_a_manifest_and_the_chunks_join_without_duplicates(
    recordings: dict[str, Path], tmp_path: Path
):
    out = tmp_path / "out"
    model = ScriptedPose(lambda pos: [PERSON], by_pixel=False)

    manifest = run_pose_pass(recordings, out, model, n=1, chunk_s=0.9)

    video = manifest["videos"]["d20-v9"]
    assert manifest["n"] == 1 and len(video["chunks"]) == 2 and video["n_frames"] == 60
    assert [c["file"] for c in video["chunks"]] == ["d20-v9_000.npz", "d20-v9_001.npz"]
    assert read_pass(out) == json.loads((out / "pass.json").read_text(encoding="utf-8"))
    assert "source" not in json.dumps(manifest) and str(tmp_path) not in json.dumps(manifest)  # no path, no file name
    kept = []
    for i, c in enumerate(video["chunks"]):
        raw = load_chunk(out, "d20-v9", i)
        assert raw.params.detect_every_n == 1
        mask = chunk_frame_mask(raw.t_sec, c["start_s"], c["end_s"], first=i == 0, last=i == len(video["chunks"]) - 1)
        kept.extend(raw.frame_index[mask].tolist())
    assert kept == list(range(60))  # every frame of the video once, in order


def test_t_audit_07_a_second_pass_skips_the_chunks_that_exist(recordings: dict[str, Path], tmp_path: Path):
    out = tmp_path / "out"
    run_pose_pass(recordings, out, ScriptedPose(lambda pos: [PERSON], by_pixel=False), chunk_s=0.9)
    second = ScriptedPose(lambda pos: [PERSON], by_pixel=False)

    manifest = run_pose_pass(recordings, out, second, chunk_s=0.9)

    assert second.detect_calls == [] and len(manifest["videos"]["d20-v9"]["chunks"]) == 2
    chunk_path(out, "d20-v9", 1).unlink()  # one chunk is missing: only that one is run again
    third = ScriptedPose(lambda pos: [PERSON], by_pixel=False)
    run_pose_pass(recordings, out, third, chunk_s=0.9)
    assert len(third.detect_calls) > 0 and chunk_path(out, "d20-v9", 1).exists()


def test_t_audit_07_a_missing_pass_or_chunk_is_an_audit_error(tmp_path: Path):
    with pytest.raises(AuditError, match="pass.json"):
        read_pass(tmp_path)
    (tmp_path / "pass.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(AuditError, match="version"):
        read_pass(tmp_path)
    with pytest.raises(AuditError, match="missing"):
        load_chunk(tmp_path, "d20-v1", 0)
