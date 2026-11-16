"""T-SYNC-04, 04b..d: flash validation using brightness jumps and residual calculation (W2 step 4, P2.05)."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import scipy.io.wavfile

from taiji_ai.config import Settings
from taiji_ai.io.audio_sync import estimate_sync
from taiji_ai.io.flash import (
    brightness_series,
    find_flash_onsets,
    validate_sync,
)
from taiji_ai.io.frames import scan_pts_ticks
from taiji_ai.io.ingest import ingest_recording

FFMPEG = shutil.which("ffmpeg")


def _make_video_with_flashes(
    video_path: Path,
    duration: float = 5.0,
    fps: int = 30,
    flashes: tuple[tuple[int, int], ...] = ((45, 60),),
    vfr: bool = False,
    ramp: bool = False,
    audio_claps: tuple[float, ...] | None = None,
    audio_delay_s: float = 0.0,
) -> None:
    """Generate synthetic video clip with controlled white flash frames, optional audio claps and VFR timestamps."""
    vf_filters: list[str] = []

    if ramp:
        vf_filters.append("eq=brightness='min(0.8,t*0.2)'")
    else:
        for start_f, end_f in flashes:
            vf_filters.append(f"drawbox=enable='between(n,{start_f},{end_f})':color=white:t=fill")

    if vfr:
        vf_filters.append(r"select='lt(n\,30)+not(mod(n\,3))'")

    filter_str = ",".join(vf_filters) if vf_filters else "null"

    inputs: list[str] = [
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=64x48:rate={fps}:duration={duration:.2f}",
    ]

    wav_tmp: Path | None = None
    if audio_claps is not None:
        sr = 16000
        n_samples = int(duration * sr)
        audio = np.random.default_rng(42).normal(0, 0.002, n_samples).astype(np.float32)
        for c in audio_claps:
            idx = int((c + audio_delay_s) * sr)
            pulse_len = int(0.005 * sr)
            pulse = np.sin(2 * np.pi * 1200 * np.arange(pulse_len) / sr) * np.exp(-np.linspace(0, 5, pulse_len))
            if 0 <= idx and idx + pulse_len <= n_samples:
                audio[idx : idx + pulse_len] += pulse.astype(np.float32)
        audio = np.clip(audio, -1.0, 1.0)
        wav_tmp = video_path.with_suffix(".tmp.wav")
        scipy.io.wavfile.write(str(wav_tmp), sr, (audio * 32767.0).astype(np.int16))
        inputs.extend(["-i", str(wav_tmp)])

    cmd = [
        FFMPEG,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *inputs,
        "-vf",
        filter_str,
    ]
    if vfr:
        cmd.extend(["-fps_mode", "vfr"])
    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
        ]
    )
    if audio_claps is not None:
        cmd.extend(["-c:a", "aac", "-shortest"])
    else:
        cmd.append("-an")
    cmd.append(str(video_path))

    subprocess.run(cmd, check=True)
    if wav_tmp is not None and wav_tmp.exists():
        wav_tmp.unlink()


def _ingest_pair(
    video_a: Path,
    video_b: Path,
    settings: Settings,
    take_id: str = "S01-P03-T01",
) -> tuple[Path, Path]:
    meta_a = {
        "participant_id": "P03",
        "session_id": "S01",
        "take_id": take_id,
        "camera_id": "camA",
    }
    meta_b = {
        "participant_id": "P03",
        "session_id": "S01",
        "take_id": take_id,
        "camera_id": "camB",
    }
    res_a = ingest_recording(video_a, meta_a, settings)
    res_b = ingest_recording(video_b, meta_b, settings)
    dir_a = settings.data_dir / "recordings" / res_a.manifest.recording_id
    dir_b = settings.data_dir / "recordings" / res_b.manifest.recording_id
    return dir_a, dir_b


# --- Unit and Contract Tests ---------------------------------------------------------------------------------------


def test_brightness_series_and_find_flash_onsets(tmp_path: Path):
    vid = tmp_path / "flash_unit.mp4"
    _make_video_with_flashes(vid, duration=4.0, fps=30, flashes=((45, 60),))

    ts, luma = brightness_series(vid, step=4)
    assert len(ts) == len(luma)
    assert len(ts) > 100
    assert np.all(np.diff(ts) > 0)  # Monotonic timestamps

    onsets = find_flash_onsets(ts, luma)
    assert len(onsets) == 1
    # Frame 45 at 30 fps CFR is 45 / 30 = 1.500 s
    assert abs(onsets[0] - ts[45]) < 1e-4


def test_t_sync_04_flash_exact_frame_cfr_and_vfr(tmp_path: Path):
    """T-SYNC-04: flash onset from frame 45 is found at frame 45 exactly in CFR and VFR."""
    # 1. CFR
    vid_cfr = tmp_path / "flash_cfr.mp4"
    _make_video_with_flashes(vid_cfr, duration=4.0, fps=30, flashes=((45, 60),), vfr=False)
    scan_cfr = scan_pts_ticks(vid_cfr)
    ts_cfr, luma_cfr = brightness_series(vid_cfr)
    onsets_cfr = find_flash_onsets(ts_cfr, luma_cfr)
    assert len(onsets_cfr) == 1
    expected_cfr_t = scan_cfr.t_sec[45]
    assert abs(onsets_cfr[0] - expected_cfr_t) < 1e-4

    # 2. VFR
    vid_vfr = tmp_path / "flash_vfr.mp4"
    _make_video_with_flashes(vid_vfr, duration=4.0, fps=30, flashes=((45, 60),), vfr=True)
    scan_vfr = scan_pts_ticks(vid_vfr)
    ts_vfr, luma_vfr = brightness_series(vid_vfr)
    onsets_vfr = find_flash_onsets(ts_vfr, luma_vfr)
    assert len(onsets_vfr) == 1
    # Frame 45 was retained in the VFR video at timestamp 45 / 30 = 1.500 s
    assert abs(onsets_vfr[0] - 1.5) < 1e-4
    assert any(abs(t - onsets_vfr[0]) < 1e-4 for t in scan_vfr.t_sec)


def test_t_sync_04b_slow_brightness_ramp(tmp_path: Path):
    """T-SYNC-04b: a slow brightness ramp gives no onset."""
    vid_ramp = tmp_path / "ramp.mp4"
    _make_video_with_flashes(vid_ramp, duration=4.0, fps=30, ramp=True)

    ts, luma = brightness_series(vid_ramp)
    onsets = find_flash_onsets(ts, luma)
    assert len(onsets) == 0


def test_t_sync_04c_residual_known_offset_and_wrong_offset(tmp_path: Path, ingest_settings: Settings):
    """T-SYNC-04c: residual <= 1 frame on matched cameras; perturbed offset gives ~ 3 frames residual."""
    dur = 15.0
    fps = 30
    delta_s = 0.500  # 15 frames at 30 fps
    delta_frames = int(delta_s * fps)

    # Flashes at frames (60, 90) [start] and (360, 390) [end] on Camera A
    flashes_a = ((60, 75), (90, 105), (360, 375), (390, 405))
    claps_a = (60 / fps, 90 / fps, 360 / fps, 390 / fps)

    # Flashes and claps on Camera B are delayed by delta_s (delta_frames = 15)
    flashes_b = tuple((f0 + delta_frames, f1 + delta_frames) for f0, f1 in flashes_a)
    claps_b = tuple(c + delta_s for c in claps_a)

    vid_a = tmp_path / "vid_sync_a.mp4"
    vid_b = tmp_path / "vid_sync_b.mp4"
    _make_video_with_flashes(vid_a, duration=dur, fps=fps, flashes=flashes_a, audio_claps=claps_a)
    _make_video_with_flashes(vid_b, duration=dur, fps=fps, flashes=flashes_b, audio_claps=claps_b)

    dir_a, dir_b = _ingest_pair(vid_a, vid_b, ingest_settings, take_id="S01-P03-T01")

    audio_sync = estimate_sync(dir_a, dir_b)
    assert audio_sync.status == "ok"
    assert audio_sync.offset_s is not None
    assert abs(audio_sync.offset_s - delta_s) < 0.005

    # 1. Valid sync -> residual <= 1 frame
    val = validate_sync(audio_sync, dir_a, dir_b)
    assert val.method == "flash"
    assert val.residual_ms is not None
    assert val.residual_frames is not None
    assert val.residual_frames <= 1.0  # within 1 frame
    assert len(val.flash_a_s) >= 2
    assert len(val.flash_b_s) >= 2

    # 2. Deliberately perturbed offset by 3 frames (3 / 30 = 0.100 s)
    perturb_s = 3.0 / float(fps)
    audio_sync_wrong = replace(audio_sync, offset_s=audio_sync.offset_s + perturb_s)
    val_wrong = validate_sync(audio_sync_wrong, dir_a, dir_b)
    assert val_wrong.method == "flash"
    assert val_wrong.residual_frames is not None
    # Expect residual around 3 frames (+- 0.5 frame)
    assert abs(val_wrong.residual_frames - 3.0) < 0.5


def test_t_sync_04d_no_flash(tmp_path: Path, ingest_settings: Settings):
    """T-SYNC-04d: no flash gives validation 'none' and null residuals."""
    dur = 10.0
    fps = 30
    claps = (2.0, 3.0, 7.0, 8.0)

    # Videos with sound claps but no flash overlays
    vid_a = tmp_path / "vid_noflash_a.mp4"
    vid_b = tmp_path / "vid_noflash_b.mp4"
    _make_video_with_flashes(vid_a, duration=dur, fps=fps, flashes=(), audio_claps=claps)
    _make_video_with_flashes(vid_b, duration=dur, fps=fps, flashes=(), audio_claps=claps, audio_delay_s=0.3)

    dir_a, dir_b = _ingest_pair(vid_a, vid_b, ingest_settings, take_id="S01-P03-T02")

    audio_sync = estimate_sync(dir_a, dir_b)
    assert audio_sync.status == "ok"

    val = validate_sync(audio_sync, dir_a, dir_b)
    assert val.method == "none"
    assert val.residual_start_ms is None
    assert val.residual_end_ms is None
    assert val.residual_ms is None
    assert val.residual_frames is None
    assert val.flash_a_s == ()
    assert val.flash_b_s == ()
