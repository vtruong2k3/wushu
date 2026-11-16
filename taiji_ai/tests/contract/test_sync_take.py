"""T-SYNC-05c, T-SYNC-05d: Contract tests for sync_take and CLI taiji sync (W2 step 5, P2.06)."""

from __future__ import annotations

import shutil
import subprocess
from contextlib import closing
from pathlib import Path

import numpy as np
import pytest
import scipy.io.wavfile

from taiji_ai.cli import main
from taiji_ai.config import Settings
from taiji_ai.io.ingest import ingest_recording
from taiji_ai.pipeline.sync_take import SyncTakeError, sync_take
from taiji_ai.schemas._base import read_manifest
from taiji_ai.schemas.sync import SyncManifest
from taiji_ai.store.db import connect
from taiji_ai.store.sync import find_sync

pytestmark = pytest.mark.usefixtures("clean_logging")

FFMPEG = shutil.which("ffmpeg")


def _make_video_pair(
    tmp_path: Path,
    settings: Settings,
    take_id: str = "S01-P03-T01",
    *,
    with_flashes: bool = True,
    start_only: bool = False,
    single_camera: bool = False,
) -> tuple[Path, Path | None]:
    """Create and ingest a take with two cameras (camA, camB) with audio claps and optional flash markers."""
    dur = 12.0
    fps = 30
    delta_s = 0.500
    delta_frames = int(delta_s * fps)

    # Claps at start (2.0s, 3.0s) and end (9.0s, 10.0s) on Camera A
    claps_a = [2.0, 3.0]
    flashes_a = [(60, 75), (90, 105)]
    if not start_only:
        claps_a += [9.0, 10.0]
        flashes_a += [(270, 285), (300, 315)]

    claps_b = [c + delta_s for c in claps_a]
    flashes_b = [(f0 + delta_frames, f1 + delta_frames) for f0, f1 in flashes_a]

    def _make_clip(out_path: Path, claps: list[float], flashes: list[tuple[int, int]]) -> None:
        sr = 16000
        n_samples = int(dur * sr)
        audio = np.random.default_rng(42).normal(0, 0.002, n_samples).astype(np.float32)
        for c in claps:
            idx = int(c * sr)
            pulse_len = int(0.005 * sr)
            pulse = np.sin(2 * np.pi * 1200 * np.arange(pulse_len) / sr) * np.exp(-np.linspace(0, 5, pulse_len))
            if 0 <= idx and idx + pulse_len <= n_samples:
                audio[idx : idx + pulse_len] += pulse.astype(np.float32)
        audio = np.clip(audio, -1.0, 1.0)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        wav_tmp = out_path.with_suffix(".tmp.wav")
        scipy.io.wavfile.write(str(wav_tmp), sr, (audio * 32767.0).astype(np.int16))

        vf_filters: list[str] = []
        if with_flashes:
            for start_f, end_f in flashes:
                vf_filters.append(f"drawbox=enable='between(n,{start_f},{end_f})':color=white:t=fill")
        filter_str = ",".join(vf_filters) if vf_filters else "null"

        cmd = [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=64x48:rate={fps}:duration={dur:.2f}",
            "-i",
            str(wav_tmp),
            "-vf",
            filter_str,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(out_path),
        ]
        subprocess.run(cmd, check=True)
        wav_tmp.unlink()

    file_a = tmp_path / "vid_a.mp4"
    _make_clip(file_a, claps_a, flashes_a)
    meta_a = {"participant_id": "P03", "session_id": "S01", "take_id": take_id, "camera_id": "camA"}
    res_a = ingest_recording(file_a, meta_a, settings)
    dir_a = settings.data_dir / "recordings" / res_a.manifest.recording_id

    if single_camera:
        return dir_a, None

    file_b = tmp_path / "vid_b.mp4"
    _make_clip(file_b, claps_b, flashes_b)
    meta_b = {"participant_id": "P03", "session_id": "S01", "take_id": take_id, "camera_id": "camB"}
    res_b = ingest_recording(file_b, meta_b, settings)
    dir_b = settings.data_dir / "recordings" / res_b.manifest.recording_id

    return dir_a, dir_b


def test_t_sync_05c_sync_take_ok_and_start_only(tmp_path: Path, ingest_settings: Settings):
    """T-SYNC-05c: sync_take writes sync.json and SQLite row for ok; start_only writes sync.json without SQLite row."""
    # 1. Take with ok sync and flash validation -> writes sync.json and SQLite sync row
    take_ok = "S01-P03-T01"
    _make_video_pair(tmp_path / "pair_ok", ingest_settings, take_id=take_ok, with_flashes=True, start_only=False)

    manifest = sync_take(take_ok, settings=ingest_settings)
    assert manifest.status == "ok"
    assert manifest.usable_for_metrics is True
    assert manifest.usable_reason == "usable"

    manifest_file = ingest_settings.data_dir / "takes" / take_ok / "sync.json"
    assert manifest_file.is_file()
    read_back = read_manifest(manifest_file, SyncManifest)
    assert read_back == manifest

    # Check SQLite row
    with closing(connect(ingest_settings.db_path, ingest_settings.migrations_dir)) as conn:
        row = find_sync(conn, take_ok, "camA", "camB")
        assert row is not None
        assert row["take_id"] == take_ok
        assert row["cam_a"] == "camA"
        assert row["cam_b"] == "camB"
        assert abs(row["offset_s"] - 0.500) < 0.010
        assert row["method"] == "audio_xcorr/1"
        assert row["validated_by"] == "flash"
        assert row["residual_ms"] is not None

    # 2. Take with start_only -> writes sync.json but NO row in SQLite sync
    take_start = "S01-P03-T02"
    _make_video_pair(tmp_path / "pair_start", ingest_settings, take_id=take_start, with_flashes=True, start_only=True)

    manifest_start = sync_take(take_start, settings=ingest_settings)
    assert manifest_start.status == "start_only"
    assert manifest_start.usable_for_metrics is False
    assert manifest_start.usable_reason == "start_only"

    manifest_file_start = ingest_settings.data_dir / "takes" / take_start / "sync.json"
    assert manifest_file_start.is_file()
    read_back_start = read_manifest(manifest_file_start, SyncManifest)
    assert read_back_start == manifest_start

    with closing(connect(ingest_settings.db_path, ingest_settings.migrations_dir)) as conn:
        row_start = find_sync(conn, take_start, "camA", "camB")
        assert row_start is None


def test_t_sync_05d_missing_camera_refusal(tmp_path: Path, ingest_settings: Settings):
    """T-SYNC-05d: a take with a missing camera gives clear error and nothing written."""
    take_single = "S01-P03-T03"
    _make_video_pair(tmp_path / "single", ingest_settings, take_id=take_single, single_camera=True)

    with pytest.raises(SyncTakeError, match="exactly two required"):
        sync_take(take_single, settings=ingest_settings)

    manifest_file = ingest_settings.data_dir / "takes" / take_single / "sync.json"
    assert not manifest_file.exists()

    with closing(connect(ingest_settings.db_path, ingest_settings.migrations_dir)) as conn:
        row = find_sync(conn, take_single, "camA", "camB")
        assert row is None


def test_cli_sync_command(tmp_path: Path, ingest_settings: Settings, capsys: pytest.CaptureFixture[str]):
    """CLI taiji sync: exit 0 on usable take, exit 1 on unusable or non-existent take."""
    # 1. Non-existent take -> exit 1, error on stderr
    code = main(["sync", "S01-P03-T99"], settings=ingest_settings)
    captured = capsys.readouterr()
    assert code == 1
    assert "error: take S01-P03-T99: no recordings found" in captured.err

    # 2. Usable take -> exit 0, sync info on stdout
    take_ok = "S01-P03-T04"
    _make_video_pair(tmp_path / "cli_ok", ingest_settings, take_id=take_ok, with_flashes=True, start_only=False)
    code_ok = main(["sync", take_ok], settings=ingest_settings)
    captured_ok = capsys.readouterr()
    assert code_ok == 0
    assert f"sync {take_ok} (camA <-> camB): ok, usable=True (usable)" in captured_ok.out

    # 3. Unusable take (start_only) -> exit 1, sync info on stdout
    take_unusable = "S01-P03-T05"
    _make_video_pair(
        tmp_path / "cli_unusable", ingest_settings, take_id=take_unusable, with_flashes=True, start_only=True
    )
    code_unusable = main(["sync", take_unusable], settings=ingest_settings)
    captured_unusable = capsys.readouterr()
    assert code_unusable == 1
    assert f"sync {take_unusable} (camA <-> camB): start_only, usable=False (start_only)" in captured_unusable.out
