"""Synthetic two-camera takes with controlled flashes and claps, for the flash-pair tests (X.23, BUG-0064).

A take has 15 s at 30 fps. Claps (two bursts 1 s apart) are always made for both cameras, so the audio sync is ``ok``;
the flashes (0.5 s of white, drawn on the video) are given per camera, in the camera's own video time, so a test can
hide any flash of any camera. Camera B is delayed by ``delta_s`` (its claps, and the flashes the caller lists for it,
are expected ``delta_s`` later), so the true offset is ``delta_s``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import scipy.io.wavfile

from helpers.sync_media import FFMPEG, SR, clap_audio
from taiji_ai.config import Settings
from taiji_ai.io.ingest import ingest_recording

FPS = 30
DURATION_S = 15.0
FLASH_S = 0.5  # a flash stays on for half a second, whatever the frame rate
# Flash pairs of camera A (seconds on A's video time): the start pair and the end pair, 1 s apart.
PAIRS_A = (2.0, 3.0, 12.0, 13.0)


def _write_video(
    path: Path, flashes_s: tuple[float, ...], claps_s: tuple[float, ...], seed: int, fps: int = FPS
) -> None:
    assert FFMPEG, "ffmpeg not on PATH"
    audio = clap_audio(DURATION_S, claps_s, seed=seed)
    wav = path.with_suffix(".tmp.wav")
    scipy.io.wavfile.write(str(wav), SR, (audio * 32767.0).astype(int).astype("int16"))
    on_frames = max(1, round(FLASH_S * fps))
    boxes = [
        f"drawbox=enable='between(n,{n},{n + on_frames - 1})':color=white:t=fill"
        for n in (round(t * fps) for t in flashes_s)
    ]
    vf = ",".join(boxes) if boxes else "null"
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    cmd += ["-f", "lavfi", "-i", f"testsrc2=size=64x48:rate={fps}:duration={DURATION_S:.2f}", "-i", str(wav)]
    cmd += ["-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-shortest", str(path)]
    subprocess.run(cmd, check=True)
    wav.unlink()


def make_flash_take(
    tmp_path: Path,
    settings: Settings,
    *,
    flashes_a: tuple[float, ...] = PAIRS_A,
    flashes_b: tuple[float, ...] | None = None,
    delta_s: float = 0.5,
    fps_b: int = FPS,
    take_id: str = "S01-P03-T01",
) -> tuple[Path, Path]:
    """Make and ingest camera A and camera B of one take; returns their recording folders.

    ``flashes_a`` are flash onsets on A's video time. ``flashes_b`` are onsets on B's video time; by default they are
    ``flashes_a`` moved by ``delta_s`` (every flash seen by both cameras).
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    flashes_b = tuple(t + delta_s for t in flashes_a) if flashes_b is None else flashes_b
    claps_a = PAIRS_A
    claps_b = tuple(t + delta_s for t in PAIRS_A)
    file_a, file_b = tmp_path / "a.mov", tmp_path / "b.mov"
    _write_video(file_a, flashes_a, claps_a, seed=1)
    _write_video(file_b, flashes_b, claps_b, seed=2, fps=fps_b)
    dirs = []
    for cam, f in (("camA", file_a), ("camB", file_b)):
        meta = {"participant_id": "P03", "session_id": "S01", "take_id": take_id, "camera_id": cam}
        rec = ingest_recording(f, meta, settings)
        dirs.append(settings.data_dir / "recordings" / rec.manifest.recording_id)
    return dirs[0], dirs[1]
