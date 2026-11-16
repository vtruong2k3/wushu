"""T-AUDIT-06: from two passes to sheets, candidates and a review file, and back to the tables (P3.08).

A scripted fake model on the synthetic video (320 x 240, 60 frames, one standing person): no GPU, no model file, no D20.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest

from helpers.fake_pose import ScriptedPose, standing_person
from taiji_ai.audit import AuditError
from taiji_ai.audit.analyse import Pool, _check_aligned, analyse, collect_pass, report
from taiji_ai.audit.labels import COLUMNS, read_review
from taiji_ai.audit.scan import run_pose_pass
from taiji_ai.config import Settings
from taiji_ai.io.ingest import ingest_recording

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")

PERSON = standing_person()
RULES = {
    "low_essential", "structure", "jump", "bone", "swap_pair", "find_back", "find_one_leg", "find_rotation",
    "find_occlusion", "target_event", "cadence_diff",
}  # fmt: skip
SMALL = {"k": 3, "blind_k": 3, "min_gap_s": 0.3, "tile_size": 96}


@pytest.fixture
def recordings(cfr_video: Path, ingest_settings: Settings) -> dict[str, Path]:
    meta = {"participant_id": "P03", "session_id": "S01", "take_id": "S01-P03-T01", "camera_id": "camA"}
    rec = ingest_recording(cfr_video, meta, ingest_settings)
    return {"d20-v9": ingest_settings.data_dir / "recordings" / rec.manifest.recording_id}


def make_passes(recordings: dict[str, Path], out: Path, persons: bool = True) -> None:
    for n, folder in ((1, out), (5, out / "n5")):
        model = ScriptedPose((lambda pos: [PERSON]) if persons else (lambda pos: []), by_pixel=False)
        run_pose_pass(recordings, folder, model, n=n, chunk_s=0.9)


@pytest.fixture
def work(ingest_settings: Settings) -> Path:
    return ingest_settings.data_dir.parent  # the folder that holds data/recordings, as in the tool


def test_t_audit_06_the_analysis_writes_sheets_candidates_signals_and_an_empty_review_file(
    recordings: dict[str, Path], work: Path, tmp_path: Path
):
    out = tmp_path / "out"
    make_passes(recordings, out)

    result = analyse(out, work, **SMALL)

    candidates = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert result["n_candidates"] == len(candidates) >= 3
    assert [c["id"] for c in candidates] == [f"fc-{i:03d}" for i in range(1, len(candidates) + 1)]
    assert all(c["video"] == "d20-v9" and 0 <= c["frame_index"] < 60 for c in candidates)
    assert all(len(c["scores_n1"]) == 26 and len(c["scores_n5"]) == 26 for c in candidates)
    assert any(c["tags"] == ["blind"] for c in candidates) and any("jump" in c["tags"] for c in candidates)
    sheet = cv2.imread(str(out / "sheets" / "sheet_01.png"))
    assert sheet is not None and sheet.shape[0] > 96 and sheet.shape[1] >= 96 * min(4, len(candidates))
    assert result["n_sheets"] >= 1 and (out / "sheets" / "strips_01.png").exists()  # a jump candidate has its strip
    signals = json.loads((out / "signals.json").read_text(encoding="utf-8"))
    assert set(signals["per_rule"]) == RULES and signals["frames"] == 60
    assert signals["per_video"]["d20-v9"]["tracked_n1"] == 60 and signals["chunks_without_target_n1"] == []
    rows = read_review(out / "review.csv", expected_ids=[c["id"] for c in candidates], require_agent=False)
    assert len(rows) == len(candidates) and all(r.a.verdict == "" for r in rows)
    text = (out / "candidates.json").read_text(encoding="utf-8") + (out / "signals.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in text and "source" not in text and ".mp4" not in text  # labels and numbers only


def test_t_audit_06_a_review_file_is_never_overwritten_without_force(
    recordings: dict[str, Path], work: Path, tmp_path: Path
):
    out = tmp_path / "out"
    make_passes(recordings, out)
    analyse(out, work, **SMALL)
    (out / "review.csv").write_text("my work", encoding="utf-8")

    with pytest.raises(AuditError, match="review.csv exists"):
        analyse(out, work, **SMALL)
    assert (out / "review.csv").read_text(encoding="utf-8") == "my work"
    analyse(out, work, force=True, **SMALL)
    assert (out / "review.csv").read_text(encoding="utf-8").startswith("id,video,frame_index")


def test_t_audit_06_nobody_in_the_video_gives_no_candidates_and_no_crash(
    recordings: dict[str, Path], work: Path, tmp_path: Path
):
    out = tmp_path / "out"
    make_passes(recordings, out, persons=False)
    result = analyse(out, work, **SMALL)
    assert result["n_candidates"] == 0 and result["n_sheets"] == 0
    assert result["signals"]["chunks_without_target_n1"] and result["signals"]["cadence_diff_max"] is None
    assert json.loads((out / "candidates.json").read_text(encoding="utf-8")) == []
    pool = collect_pass(out)
    assert not pool.tracked.any() and len(pool.video) == 60 and pool.no_target


def test_t_audit_06_the_two_passes_must_cover_the_same_frames():
    a, b = Pool(), Pool()
    a.video, b.video = ["d20-v1"] * 3, ["d20-v1"] * 3
    a.frame_index, b.frame_index = np.arange(3), np.arange(3)
    a.t_sec, b.t_sec = np.arange(3) / 30.0, np.arange(3) / 30.0
    _check_aligned(a, b)
    b.frame_index = np.array([0, 1, 3])
    with pytest.raises(AuditError, match="same frames"):
        _check_aligned(a, b)
    b.frame_index, b.video = np.arange(3), ["d20-v2"] * 3
    with pytest.raises(AuditError, match="same frames"):
        _check_aligned(a, b)


def fill(out: Path, failure_id: str | None) -> list[dict[str, str]]:
    """The agent's labels: every frame ok, but ``failure_id`` (an S1 left/right swap that only N = 5 shows)."""
    with (out / "review.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if r["id"] == failure_id:
            r.update(
                a_verdict="failure", a_type="lr_swap", a_joints="LWrist|RWrist", a_severity="S1", a_view="front",
                a_situation="none", a_cadence="n5_only", h_confirmed="yes",
            )  # fmt: skip
        else:
            r.update(a_verdict="ok", a_view="front", a_situation="none")
    with (out / "review.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def test_t_audit_06_the_report_reads_the_review_and_takes_the_score_of_the_cadence_that_is_wrong(
    recordings: dict[str, Path], work: Path, tmp_path: Path
):
    out = tmp_path / "out"
    make_passes(recordings, out)
    analyse(out, work, **SMALL)
    candidates = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    blind_id = next(c["id"] for c in candidates if c["tags"] == ["blind"])
    # the score of the N = 5 skeleton of that frame is made low in the candidate list: the mask would remove the failure
    for c in candidates:
        if c["id"] == blind_id:
            c["scores_n5"] = [0.1] * 26
    (out / "candidates.json").write_text(json.dumps(candidates), encoding="utf-8")
    fill(out, blind_id)

    summary = report(out)

    assert summary["n_rows"] == len(candidates) and summary["n_failures"] == 1 and summary["blind"]["failures"] == 1
    assert summary["by_type"] == {"lr_swap": 1} and summary["cadence"] == {"n5_only": 1}
    assert (
        summary["score"]["failures_with_joints"] == 1 and summary["score"]["not_warned"] == 0
    )  # the N = 5 scores were used
    assert summary["agreement"]["verdict"] == [1, 1]
    tables = (out / "report_tables.md").read_text(encoding="utf-8")
    assert "### Every failure case" in tables and blind_id in tables and (out / "summary.json").exists()
    assert str(tmp_path) not in tables and ".mp4" not in tables


def test_t_audit_06_the_report_refuses_an_unfinished_review_and_a_missing_candidate_list(
    recordings: dict[str, Path], work: Path, tmp_path: Path
):
    out = tmp_path / "out"
    with pytest.raises(AuditError, match="candidates.json"):
        report(out)
    make_passes(recordings, out)
    analyse(out, work, **SMALL)
    with pytest.raises(AuditError, match="verdict is missing"):
        report(out)  # the template is empty


def test_t_audit_06_passes_over_different_videos_are_refused_by_the_analysis(
    recordings: dict[str, Path], work: Path, tmp_path: Path
):
    out = tmp_path / "out"
    run_pose_pass(recordings, out, ScriptedPose(lambda pos: [PERSON], by_pixel=False), n=1, chunk_s=0.9)
    other = {"d20-v8": recordings["d20-v9"]}  # the same recording under another label: not the same video
    run_pose_pass(other, out / "n5", ScriptedPose(lambda pos: [PERSON], by_pixel=False), n=5, chunk_s=0.9)
    with pytest.raises(AuditError, match="same frames"):
        analyse(out, work, **SMALL)
    assert not (out / "review.csv").exists()  # nothing was written before the check
