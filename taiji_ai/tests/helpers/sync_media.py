"""Synthetic two-camera takes with a known truth, for the audio-sync tests (P2.04).

Time model (everything in seconds):

* the *global* timeline is the real world; camera A records ``[0, end_a]``, camera B records ``[start_b, end_b]``;
* a clap pair (two 5 ms bursts ``pair_gap_s`` apart) is made 6 s after the later start (start pair) and 7 s before the
  earlier stop (end pair), the capture protocol's margins; either pair can be left out;
* the *audio file* of a camera starts with that camera; B's clock runs at ``1 + drift`` times the real one;
* ``audio_itsoffset_*`` (container option) delays the audio **in the container** by that many seconds, so
  ``audio.start_offset_s`` of that camera becomes that value (audio start minus video start): the video time of
  an event is its audio-file time plus the offset;
* the offset of the sync (``t_b - t_a`` on the two video timelines) therefore is, for an A video time ``t``::

      truth_offset(t) = drift * t - (audio_itsoffset_a + start_b) * (1 + drift) + audio_itsoffset_b

  and ``drift`` is the true drift of the mapping ``t_b = t_a + offset + drift * (t_a - t_ref)``.

Files are ``.mov`` with PCM audio by default (exact sample timing, no encoder delay); ``container=".mp4"`` uses AAC.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import scipy.io.wavfile

from taiji_ai.config import Settings
from taiji_ai.io.ingest import ingest_recording

SR = 16000
FFMPEG = shutil.which("ffmpeg")


def clap_audio(
    duration_s: float,
    clap_times_s: list[float] | tuple[float, ...],
    *,
    seed: int,
    scale: float = 1.0,
    noise_std: float = 0.002,
    amplitude: float = 1.0,
    tone_hz: float | None = None,
) -> np.ndarray:
    """Mono float32 audio at 16 kHz: Gaussian noise, an optional tone, and a 5 ms 1.2 kHz burst at each clap time.

    ``clap_times_s`` are in the camera's own audio-file time; ``scale`` stretches them (a clock that runs fast or slow).
    """
    n = int(round(duration_s * SR))
    rng = np.random.default_rng(seed)
    x = rng.normal(0.0, noise_std, n).astype(np.float32)
    if tone_hz is not None:
        x += (0.05 * np.sin(2 * np.pi * tone_hz * np.arange(n) / SR)).astype(np.float32)
    pulse_len = int(0.005 * SR)
    pulse = (np.sin(2 * np.pi * 1200 * np.arange(pulse_len) / SR) * np.exp(-np.linspace(0, 5, pulse_len))).astype(
        np.float32
    )
    for c in clap_times_s:
        i = int(round(c * scale * SR))
        if 0 <= i and i + pulse_len <= n:
            x[i : i + pulse_len] += amplitude * pulse
    return np.clip(x, -1.0, 1.0)


def write_camera_file(
    path: Path,
    audio: np.ndarray,
    *,
    audio_itsoffset: float = 0.0,
    video_fps: int = 10,
) -> Path:
    """A 64x48 test video with this audio. ``.mov`` gets PCM audio, ``.mp4`` gets AAC."""
    assert FFMPEG, "ffmpeg not on PATH"
    wav = path.with_suffix(".tmp.wav")
    scipy.io.wavfile.write(str(wav), SR, (audio * 32767.0).astype(np.int16))
    video_s = audio.size / SR + max(0.0, audio_itsoffset)
    codec = "aac" if path.suffix.lower() == ".mp4" else "pcm_s16le"
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    cmd += ["-f", "lavfi", "-i", f"testsrc2=size=64x48:rate={video_fps}:duration={video_s:.3f}"]
    if audio_itsoffset:
        cmd += ["-itsoffset", f"{audio_itsoffset}"]
    cmd += ["-i", str(wav), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", codec, "-shortest", str(path)]
    subprocess.run(cmd, check=True)
    wav.unlink()
    return path


@dataclass(frozen=True)
class TakePair:
    dir_a: Path
    dir_b: Path
    start_b: float
    drift: float
    audio_itsoffset_a: float
    audio_itsoffset_b: float
    clap_times_global: tuple[float, ...]

    def truth_offset(self, t_a_video: float) -> float:
        """The true ``t_b - t_a`` (video timelines) at the A video time ``t_a_video``."""
        d = self.drift
        return d * t_a_video - (self.audio_itsoffset_a + self.start_b) * (1 + d) + self.audio_itsoffset_b

    def a_video_time_of(self, global_time: float) -> float:
        """The A video time of a global moment."""
        return global_time + self.audio_itsoffset_a


def make_take_pair(
    tmp_path: Path,
    settings: Settings,
    *,
    end_a: float,
    end_b: float,
    start_b: float = 0.5,
    drift: float = 0.0,
    pair_gap_s: float = 1.0,
    start_pair_s: float | None = None,
    end_pair_s: float | None = None,
    start_pair: bool = True,
    end_pair: bool = True,
    noise_a: float = 0.002,
    noise_b: float = 0.002,
    clap_amplitude_b: float = 1.0,
    audio_itsoffset_a: float = 0.0,
    audio_itsoffset_b: float = 0.0,
    container: str = ".mov",
    take_id: str = "S01-P03-T01",
) -> TakePair:
    """Make, ingest and return two cameras of one take (``camA`` and ``camB``), see the module docstring."""
    s0 = max(0.0, start_b) + 6.0 if start_pair_s is None else start_pair_s  # global time of the first start clap
    s1 = min(end_a, end_b) - 7.0 if end_pair_s is None else end_pair_s  # global time of the first end clap
    claps: list[float] = []
    if start_pair:
        claps += [s0, s0 + pair_gap_s]
    if end_pair:
        claps += [s1, s1 + pair_gap_s]
    audio_a = clap_audio(end_a, claps, seed=1, noise_std=noise_a)
    audio_b = clap_audio(
        (end_b - start_b) * (1 + drift),
        [g - start_b for g in claps],
        seed=2,
        scale=1 + drift,
        noise_std=noise_b,
        amplitude=clap_amplitude_b,
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    file_a = write_camera_file(tmp_path / f"a{container}", audio_a, audio_itsoffset=audio_itsoffset_a)
    file_b = write_camera_file(tmp_path / f"b{container}", audio_b, audio_itsoffset=audio_itsoffset_b)
    dirs = []
    for cam, f in (("camA", file_a), ("camB", file_b)):
        meta = {"participant_id": "P03", "session_id": "S01", "take_id": take_id, "camera_id": cam}
        rec = ingest_recording(f, meta, settings)
        dirs.append(settings.data_dir / "recordings" / rec.manifest.recording_id)
    return TakePair(
        dir_a=dirs[0],
        dir_b=dirs[1],
        start_b=start_b,
        drift=drift,
        audio_itsoffset_a=audio_itsoffset_a,
        audio_itsoffset_b=audio_itsoffset_b,
        clap_times_global=tuple(claps),
    )
