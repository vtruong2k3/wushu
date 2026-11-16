"""T-SYNC-01..03: audio synchronization using envelope cross-correlation (W2, P2.04)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import scipy.io.wavfile
import scipy.signal

from taiji_ai.config import Settings
from taiji_ai.io.audio import AudioError, NoAudioStream, extract_audio, read_wav
from taiji_ai.io.audio_sync import (
    envelope,
    estimate_sync,
    xcorr_lag,
)
from taiji_ai.io.ingest import ingest_recording

FFMPEG = shutil.which("ffmpeg")


def _make_audio_wave(
    duration: float = 15.0,
    sr: int = 16000,
    claps: tuple[float, ...] = (2.0, 3.0, 11.0, 12.0),
    noise_std: float = 0.002,
    tone_hz: float | None = None,
    seed: int = 42,
) -> np.ndarray:
    n_samples = int(duration * sr)
    rng = np.random.default_rng(seed)
    audio = rng.normal(0, noise_std, n_samples).astype(np.float32)
    if tone_hz is not None:
        t = np.arange(n_samples) / sr
        audio += (0.05 * np.sin(2 * np.pi * tone_hz * t)).astype(np.float32)

    for c in claps:
        idx = int(c * sr)
        pulse_len = int(0.005 * sr)  # 5 ms burst
        pulse = np.sin(2 * np.pi * 1200 * np.arange(pulse_len) / sr) * np.exp(-np.linspace(0, 5, pulse_len))
        if idx + pulse_len <= n_samples:
            audio[idx : idx + pulse_len] += pulse.astype(np.float32)
    return np.clip(audio, -1.0, 1.0)


def _make_video_with_audio(video_path: Path, audio: np.ndarray, sr: int = 16000) -> None:
    wav_path = video_path.with_suffix(".tmp.wav")
    int16_data = (audio * 32767.0).astype(np.int16)
    scipy.io.wavfile.write(str(wav_path), sr, int16_data)
    dur = float(audio.size) / float(sr)

    cmd = [
        FFMPEG,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=64x48:rate=30:duration={dur:.2f}",
        "-i",
        str(wav_path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(video_path),
    ]
    subprocess.run(cmd, check=True)
    if wav_path.exists():
        wav_path.unlink()


def _ingest_sync_pair(
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


# --- Unit tests for audio and envelope ------------------------------------------------------------------------------


def test_audio_read_and_extract_cache(tmp_path: Path, ingest_settings: Settings, cfr_video: Path):
    # Non-existent recording dir
    with pytest.raises(AudioError, match="does not exist"):
        extract_audio(tmp_path / "absent")

    # Ingest a real file with audio
    meta = {
        "participant_id": "P03",
        "session_id": "S01",
        "take_id": "S01-P03-T01",
        "camera_id": "camA",
    }
    res = ingest_recording(cfr_video, meta, ingest_settings)
    dir_a = ingest_settings.data_dir / "recordings" / res.manifest.recording_id
    wav_file = extract_audio(dir_a)
    assert wav_file.is_file()
    assert wav_file.name == "audio.wav"

    # Cached on second call
    wav_file2 = extract_audio(dir_a)
    assert wav_file2 == wav_file

    samples, sr = read_wav(wav_file)
    assert sr == 16000
    assert samples.dtype == np.float32
    assert -1.0 <= np.min(samples) and np.max(samples) <= 1.0


def test_audio_no_audio_stream_raises(tmp_path: Path, ingest_settings: Settings, vfr_video: Path):
    # vfr_video has no audio stream
    meta = {
        "participant_id": "P03",
        "session_id": "S01",
        "take_id": "S01-P03-T02",
        "camera_id": "camA",
    }
    res = ingest_recording(vfr_video, meta, ingest_settings)
    dir_a = ingest_settings.data_dir / "recordings" / res.manifest.recording_id
    with pytest.raises(NoAudioStream):
        extract_audio(dir_a)


def test_envelope_filtering():
    sr = 16000
    x = np.zeros(sr, dtype=np.float32)
    # 50 Hz low-frequency hum (should be strongly attenuated by 300 Hz high-pass)
    t = np.arange(sr) / sr
    hum = np.sin(2 * np.pi * 50 * t).astype(np.float32)
    env_hum = envelope(hum, sr, hp_hz=300.0, lp_hz=50.0)
    assert np.max(env_hum) < 0.1

    # 1 kHz pulse (should pass through high-pass and form a clean positive peak)
    pulse = np.sin(2 * np.pi * 1000 * t[:80])
    x[100:180] = pulse
    env_pulse = envelope(x, sr, hp_hz=300.0, lp_hz=50.0)
    assert np.all(env_pulse >= 0.0)
    assert np.argmax(env_pulse) >= 90


def test_xcorr_lag_parabolic_precision():
    sr = 16000
    n = sr * 2
    x = np.zeros(n, dtype=np.float32)
    x[1000:1080] = 1.0

    # Delay by exactly 500 samples (0.03125 s)
    y = np.zeros(n, dtype=np.float32)
    y[1500:1580] = 1.0

    est = xcorr_lag(x, y, sr, max_lag_s=1.0)
    assert est.found is True
    assert est.lag_s is not None
    assert abs(est.lag_s - 500.0 / sr) < 1e-4
    assert est.peak is not None and est.peak > 0.95


# --- T-SYNC-01: known click offset within +-1 ms --------------------------------------------------------------------


def test_t_sync_01_known_offset_within_one_ms(tmp_path: Path, ingest_settings: Settings):
    sr = 16000
    dur = 15.0
    delta_s = 0.737  # B is delayed by 0.737 s

    # Base audio
    audio_base = _make_audio_wave(duration=dur, sr=sr, claps=(2.0, 3.0, 11.0, 12.0))

    # Camera A has audio starting at 0
    audio_a = audio_base
    # Camera B delayed by delta_s
    delta_n = int(delta_s * sr)
    audio_b = np.pad(audio_base[: -delta_n if delta_n > 0 else None], (delta_n, 0))

    vid_a = tmp_path / "vid_a.mp4"
    vid_b = tmp_path / "vid_b.mp4"
    _make_video_with_audio(vid_a, audio_a, sr=sr)
    _make_video_with_audio(vid_b, audio_b, sr=sr)

    dir_a, dir_b = _ingest_sync_pair(vid_a, vid_b, ingest_settings, take_id="S01-P03-T03")

    result = estimate_sync(dir_a, dir_b)
    assert result.status == "ok"
    assert result.offset_s is not None
    assert result.drift is not None
    assert abs(result.offset_s - delta_s) <= 0.001  # <= 1 ms precision
    assert abs(result.drift) < 500e-6  # drift very close to 0


def test_t_sync_01b_light_noise_and_tones(tmp_path: Path, ingest_settings: Settings):
    sr = 16000
    dur = 15.0
    delta_s = 0.450

    # With 100 Hz background tone and noise
    audio_base = _make_audio_wave(duration=dur, sr=sr, claps=(2.0, 3.0, 11.0, 12.0), noise_std=0.01, tone_hz=100.0)

    audio_a = audio_base
    delta_n = int(delta_s * sr)
    audio_b = np.pad(audio_base[:-delta_n], (delta_n, 0))

    vid_a = tmp_path / "vid_a_noise.mp4"
    vid_b = tmp_path / "vid_b_noise.mp4"
    _make_video_with_audio(vid_a, audio_a, sr=sr)
    _make_video_with_audio(vid_b, audio_b, sr=sr)

    dir_a, dir_b = _ingest_sync_pair(vid_a, vid_b, ingest_settings, take_id="S01-P03-T04")

    result = estimate_sync(dir_a, dir_b)
    assert result.status == "ok"
    assert result.offset_s is not None
    assert abs(result.offset_s - delta_s) <= 0.001


# T-SYNC-01c (a real container whose audio starts later than its video) is in test_audio_sync_long.py: the first
# version of it edited recording.json by hand, which tested the arithmetic but not the container (BUG-0060).


def test_t_sync_01d_symmetry_and_order(tmp_path: Path, ingest_settings: Settings):
    sr = 16000
    dur = 10.0
    delta_s = 0.500
    audio_base = _make_audio_wave(duration=dur, sr=sr, claps=(2.0, 3.0, 7.0, 8.0))
    audio_a = audio_base
    delta_n = int(delta_s * sr)
    audio_b = np.pad(audio_base[:-delta_n], (delta_n, 0))

    vid_a = tmp_path / "vid_sym_a.mp4"
    vid_b = tmp_path / "vid_sym_b.mp4"
    _make_video_with_audio(vid_a, audio_a, sr=sr)
    _make_video_with_audio(vid_b, audio_b, sr=sr)

    dir_a, dir_b = _ingest_sync_pair(vid_a, vid_b, ingest_settings, take_id="S01-P03-T05")

    # Passing (dir_a, dir_b) vs (dir_b, dir_a) both respect cam_a < cam_b
    res1 = estimate_sync(dir_a, dir_b)
    res2 = estimate_sync(dir_b, dir_a)
    assert res1.offset_s == res2.offset_s
    assert res1.cam_a == "camA" and res1.cam_b == "camB"


# --- T-SYNC-02: drift detection on stretched/resampled audio ---------------------------------------------------------


def test_t_sync_02_resampled_audio_drift(tmp_path: Path, ingest_settings: Settings):
    sr = 16000
    dur = 16.0
    true_drift = 100e-6  # 100 ppm
    claps = (3.0, 4.0, 12.0, 13.0)

    audio_a = _make_audio_wave(duration=dur, sr=sr, claps=claps)

    # Stretch audio for B by 1 + true_drift
    n_resampled = int(audio_a.size * (1.0 + true_drift))
    audio_b_stretched = scipy.signal.resample(audio_a, n_resampled).astype(np.float32)

    delta_s = 0.300
    delta_n = int(delta_s * sr)
    audio_b = np.pad(audio_b_stretched, (delta_n, 0))[: audio_a.size]

    vid_a = tmp_path / "vid_drift_a.mp4"
    vid_b = tmp_path / "vid_drift_b.mp4"
    _make_video_with_audio(vid_a, audio_a, sr=sr)
    _make_video_with_audio(vid_b, audio_b, sr=sr)

    dir_a, dir_b = _ingest_sync_pair(vid_a, vid_b, ingest_settings, take_id="S01-P03-T06")

    result = estimate_sync(dir_a, dir_b)
    assert result.status == "ok"
    assert result.drift is not None
    # Within +-20% of true drift (80 to 120 ppm)
    assert abs(result.drift - true_drift) / true_drift < 0.20


# --- T-SYNC-03: no clicks or no audio stream ------------------------------------------------------------------------


def test_t_sync_03_no_clicks_or_no_audio(tmp_path: Path, ingest_settings: Settings, vfr_video: Path):
    sr = 16000
    dur = 10.0
    # Flat tone with no clicks
    audio_flat_a = _make_audio_wave(duration=dur, sr=sr, claps=(), tone_hz=440.0, seed=1)
    audio_flat_b = _make_audio_wave(duration=dur, sr=sr, claps=(), tone_hz=440.0, seed=2)

    vid_a = tmp_path / "vid_flat_a.mp4"
    vid_b = tmp_path / "vid_flat_b.mp4"
    _make_video_with_audio(vid_a, audio_flat_a, sr=sr)
    _make_video_with_audio(vid_b, audio_flat_b, sr=sr)

    dir_a, dir_b = _ingest_sync_pair(vid_a, vid_b, ingest_settings, take_id="S01-P03-T07")

    result = estimate_sync(dir_a, dir_b)
    assert result.status == "not_found"
    assert result.not_found_reason == "clap_not_found"
    assert result.offset_s is None
    assert result.drift is None

    # No audio stream in files
    vid_no_audio_a = tmp_path / "no_audio_a.mp4"
    vid_no_audio_b = tmp_path / "no_audio_b.mp4"
    for p, d in [(vid_no_audio_a, 4.0), (vid_no_audio_b, 4.1)]:
        subprocess.run(
            [
                FFMPEG,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc2=size=64x48:rate=30:duration={d}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(p),
            ],
            check=True,
        )
    dir_vfr_a, dir_vfr_b = _ingest_sync_pair(vid_no_audio_a, vid_no_audio_b, ingest_settings, take_id="S01-P03-T08")
    result_no_audio = estimate_sync(dir_vfr_a, dir_vfr_b)
    assert result_no_audio.status == "not_found"
    assert result_no_audio.not_found_reason == "no_audio"
