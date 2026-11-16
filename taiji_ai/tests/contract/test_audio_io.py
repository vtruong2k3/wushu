"""T-SYNC-10: audio input and output, refusals and resources of the two-camera sync (P2.04 rework, BUG-0061).

Contract under test (``Docs/tasks/P2.04.md`` section 9.3, "API" and "No made-up numbers"):

* ``extract_audio(recording_dir)`` and ``estimate_sync(rec_dir_a, rec_dir_b, *, params=None)`` have no ``settings``;
* ``audio.wav`` is a cache (no new ffmpeg run), a stereo source becomes a mono 16 kHz 16-bit wav, an ffmpeg failure or
  timeout raises ``AudioError`` with no path in the message and nothing left behind, a failed delete of the temporary
  file is logged (never swallowed, never hiding the ffmpeg error);
* ``read_wav`` returns float32 in ``[-1, 1]`` for every PCM width and raises ``AudioError`` for a missing or broken
  file;
* ``estimate_sync`` raises ``TakeMismatch`` (two different ``take_id``) and ``SyncInputError`` (unreadable manifest, a
  wav whose sample rate is not ``params.sr``); both are ``SyncError``, which is an ``AudioError``;
* one camera without an audio stream gives ``not_found`` / ``no_audio`` (no exception, no offset);
* the memory of a 10 minute take stays bounded: the envelope is computed on the windows, not on the whole recording.

The new names of the reworked code (the three exceptions) are only looked up inside the test bodies, so the file
collects on the old code and every test fails on its own merits there.
"""

from __future__ import annotations

import inspect
import io
import logging
import os
import re
import struct
import subprocess
import tracemalloc
from pathlib import Path

import numpy as np
import pytest
import scipy.io.wavfile

from helpers.sync_media import FFMPEG, SR, TakePair, clap_audio, make_take_pair, write_camera_file
from taiji_ai.config import Settings
from taiji_ai.io import audio, audio_sync
from taiji_ai.io.ingest import ingest_recording
from taiji_ai.schemas._base import read_manifest
from taiji_ai.schemas.recording import RecordingManifest

pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not available")

# Peak of Python/numpy memory allowed for the sync of a 10 minute take [MiB]. The whole-recording envelope of the old
# code peaks at about 476 MiB (tracemalloc, measured 2026-11-16); the windowed one measured 141 MiB (two decoded
# recordings of about 40 MiB each and small slices), so 250 MiB keeps a margin of 1.8 without admitting the old code.
MEMORY_LIMIT_MB = 250

SHORT_A = 12.0  # [s] A records [0, 12]
SHORT_B = 12.5  # [s] B records [0.5, 12.5]; the pair has start claps only (6.5 s and 7.5 s on the global timeline)
FAKE_STDERR = "/secret/folder/clip.mp4: Invalid data found when processing input"


def _exc(name: str) -> type[Exception]:
    """A new exception of ``taiji_ai.io.audio_sync`` (contract 9.3), or a clear failure when it does not exist yet."""
    cls = getattr(audio_sync, name, None)
    if cls is None:
        pytest.fail(f"taiji_ai.io.audio_sync.{name} is not defined (contract 9.3)")
    return cls


def _ingest(path: Path, camera_id: str, settings: Settings, take_id: str = "S01-P03-T01") -> Path:
    """Ingest one file as a camera of a take and return the recording folder."""
    meta = {"participant_id": "P03", "session_id": "S01", "take_id": take_id, "camera_id": camera_id}
    rec = ingest_recording(path, meta, settings)
    return settings.data_dir / "recordings" / rec.manifest.recording_id


def _short_pair(tmp_path: Path, settings: Settings) -> TakePair:
    """A 12 s take with start claps only; the tests that use it never look at the claps."""
    return make_take_pair(tmp_path / "media", settings, end_a=SHORT_A, end_b=SHORT_B, end_pair=False)


def _one_recording(tmp_path: Path, settings: Settings) -> Path:
    """One 8 s camera (two claps) ingested as ``camA`` of take S01-P03-T01; no wav is extracted yet."""
    media = tmp_path / "media"
    media.mkdir(parents=True, exist_ok=True)
    path = write_camera_file(media / "one.mov", clap_audio(8.0, [3.0, 4.0], seed=1))
    return _ingest(path, "camA", settings)


def _write_video_only(path: Path, duration_s: float) -> Path:
    """A 64x48 test video with no audio stream."""
    assert FFMPEG
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi"]
    cmd += ["-i", f"testsrc2=size=64x48:rate=10:duration={duration_s}", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    subprocess.run([*cmd, str(path)], check=True)
    return path


def _one_audio_pair(
    tmp_path: Path, settings: Settings, lacking: str, duration_s: float = 20.0, duration_b_s: float | None = None
) -> tuple[Path, Path]:
    """Two cameras of one take; the camera named ``lacking`` ("camA" or "camB") has a video-only file.

    A lasts ``duration_s`` and B ``duration_b_s`` (the same when it is left out).
    """
    media = tmp_path / "media"
    media.mkdir(parents=True, exist_ok=True)
    durations = {"camA": duration_s, "camB": duration_b_s or duration_s}
    files: dict[str, Path] = {}
    for seed, cam in enumerate(("camA", "camB"), start=1):
        path = media / f"{cam}.mov"
        if cam == lacking:
            files[cam] = _write_video_only(path, durations[cam])
        else:
            files[cam] = write_camera_file(path, clap_audio(durations[cam], [6.5, 7.5], seed=seed))
    return _ingest(files["camA"], "camA", settings), _ingest(files["camB"], "camB", settings)


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


# --- take mismatch and unreadable inputs ---------------------------------------------------------------------------


@pytest.mark.parametrize("swapped", [False, True], ids=["a_then_b", "b_then_a"])
def test_t_sync_10_take_mismatch_is_refused(tmp_path: Path, ingest_settings: Settings, swapped: bool) -> None:
    """Catches: a take mismatch that is a bare ValueError, is ignored, or whose message carries a path."""
    media = tmp_path / "media"
    media.mkdir()
    file_a = write_camera_file(media / "a.mov", clap_audio(SHORT_A, [6.5, 7.5], seed=1))
    file_b = write_camera_file(media / "b.mov", clap_audio(SHORT_A, [6.5, 7.5], seed=2))
    dir_a = _ingest(file_a, "camA", ingest_settings, take_id="S01-P03-T01")
    dir_b = _ingest(file_b, "camB", ingest_settings, take_id="S01-P03-T02")
    first, second = (dir_b, dir_a) if swapped else (dir_a, dir_b)

    with pytest.raises(_exc("TakeMismatch")) as info:
        audio_sync.estimate_sync(first, second)

    assert isinstance(info.value, _exc("SyncError"))
    assert isinstance(info.value, audio.AudioError)
    message = str(info.value)
    assert "S01-P03-T01" in message and "S01-P03-T02" in message
    data_dir = ingest_settings.data_dir
    for leak in (str(tmp_path), tmp_path.as_posix(), str(data_dir), data_dir.as_posix(), "/", "\\", ".mov", ".json"):
        assert leak not in message


@pytest.mark.parametrize("damage", ["missing", "garbage"])
@pytest.mark.parametrize("which", ["a", "b"])
def test_t_sync_10_unreadable_manifest_is_refused(
    tmp_path: Path, ingest_settings: Settings, which: str, damage: str
) -> None:
    """Catches: an unreadable recording.json (either camera) reported as a bare ValueError instead of SyncInputError."""
    tp = _short_pair(tmp_path, ingest_settings)
    manifest = (tp.dir_a if which == "a" else tp.dir_b) / "recording.json"
    if damage == "missing":
        manifest.unlink()
    else:
        manifest.chmod(0o666)
        manifest.write_text("{ this is not a manifest", encoding="utf-8")

    with pytest.raises(_exc("SyncInputError")) as info:
        audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    assert isinstance(info.value, _exc("SyncError"))
    assert isinstance(info.value, audio.AudioError)


def test_t_sync_10_the_same_recording_twice_is_refused(tmp_path: Path, ingest_settings: Settings) -> None:
    """Catches: a sync of a recording with itself (ok, offset 0, one camera as both A and B: no manifest takes it)."""
    tp = _short_pair(tmp_path, ingest_settings)

    with pytest.raises(_exc("SyncInputError")):
        audio_sync.estimate_sync(tp.dir_a, tp.dir_a)


def test_t_sync_10_missing_recording_folder_is_refused(tmp_path: Path, ingest_settings: Settings) -> None:
    """Catches: a recording folder that does not exist reported as a bare ValueError (its manifest is unreadable)."""
    tp = _short_pair(tmp_path, ingest_settings)

    with pytest.raises(_exc("SyncInputError")):
        audio_sync.estimate_sync(tp.dir_a, tmp_path / "absent")


# --- sample rate ---------------------------------------------------------------------------------------------------


def _write_8khz_wav(path: Path) -> None:
    t = np.arange(10 * 8000) / 8000.0
    scipy.io.wavfile.write(str(path), 8000, (0.3 * np.sin(2 * np.pi * 440.0 * t) * 32767.0).astype(np.int16))


@pytest.mark.parametrize("camera", ["camA", "camB"])
def test_t_sync_10_wav_with_another_sample_rate_is_refused(
    tmp_path: Path, ingest_settings: Settings, camera: str
) -> None:
    """Catches: no check of the sample rate (every time shifts silently), or a check that looks at one camera only."""
    tp = _short_pair(tmp_path, ingest_settings)
    target = tp.dir_a if camera == "camA" else tp.dir_b
    wav = audio.extract_audio(target)
    assert wav.name == "audio.wav"
    _write_8khz_wav(wav)

    with pytest.raises(_exc("SyncInputError")) as info:
        audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    assert re.search(r"sample.?rate|8000", str(info.value), re.IGNORECASE), str(info.value)


def test_t_sync_10_wav_rate_is_compared_with_params_sr(tmp_path: Path, ingest_settings: Settings) -> None:
    """Catches: the sample rate compared with a hard-coded 16000 instead of ``params.sr``."""
    tp = _short_pair(tmp_path, ingest_settings)
    params = audio_sync.SyncAudioParams(sr=8000)

    with pytest.raises(_exc("SyncInputError")) as info:
        audio_sync.estimate_sync(tp.dir_a, tp.dir_b, params=params)

    assert re.search(r"sample.?rate|16000|8000", str(info.value), re.IGNORECASE), str(info.value)


# --- audio.wav cache and extraction --------------------------------------------------------------------------------


def test_t_sync_10_cached_wav_runs_no_ffmpeg(
    tmp_path: Path, ingest_settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    """Catches: a cache that is ignored (ffmpeg runs again) or a file that is rewritten on the second call."""
    rec_dir = _one_recording(tmp_path, ingest_settings)
    first = audio.extract_audio(rec_dir)
    before = (first.read_bytes(), first.stat().st_mtime_ns)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("ffmpeg must not run when audio.wav exists")

    monkeypatch.setattr(audio.subprocess, "run", forbidden)
    monkeypatch.setattr(audio.subprocess, "Popen", forbidden)
    second = audio.extract_audio(rec_dir)

    assert second == first
    assert second.is_file()
    assert (second.read_bytes(), second.stat().st_mtime_ns) == before


def _mkv_with_a_hole(path: Path, hole_s: float) -> Path:
    """A 20 s camera whose audio loses ``hole_s`` at 10 s while the timestamps keep running (a dropout)."""
    assert FFMPEG
    audio_data = clap_audio(20.0, [3.0, 4.0], seed=1)
    first, count = 10 * SR, int(round(hole_s * SR))
    audio_data = np.concatenate([audio_data[:first], audio_data[first + count :]])
    wav = path.with_suffix(".tmp.wav")
    scipy.io.wavfile.write(str(wav), SR, (audio_data * 32767.0).astype(np.int16))
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi"]
    cmd += ["-i", "testsrc2=size=64x48:rate=10:duration=20", "-i", str(wav)]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le"]
    cmd += ["-af", f"asetpts='PTS+if(gte(T,10),{hole_s}/TB,0)'", "-shortest", str(path)]
    subprocess.run(cmd, check=True)
    wav.unlink()
    return path


@pytest.mark.parametrize("hole_s", [0.04, 0.12], ids=["hole_40ms", "hole_120ms"])
def test_t_sync_10_an_audio_track_with_dropped_samples_is_refused(
    tmp_path: Path, ingest_settings: Settings, hole_s: float
) -> None:
    """Catches: samples dropped by a phone (a jump of the audio timestamps) written back to back by ffmpeg, so every
    time after the gap in the wav is early by the gap: the sync would say ok with a fictitious drift (found by the
    adversarial pass: 40 ms wrong at the end claps). The take is refused with an error, nothing is written."""
    media = tmp_path / "media"
    media.mkdir()
    rec_dir = _ingest(_mkv_with_a_hole(media / "hole.mkv", hole_s), "camA", ingest_settings)
    source = next(rec_dir.glob("source.*"))
    assert abs(audio.audio_gap_s(source) - hole_s) < 0.002  # premise: the gap is in the container

    with pytest.raises(audio.AudioError, match="dropped|repeated"):
        audio.extract_audio(rec_dir)

    assert not (rec_dir / "audio.wav").exists()
    assert not list(rec_dir.glob("audio.tmp*"))


@pytest.mark.parametrize("fixture", ["cfr_video", "offset_video", "rotated_video"])
def test_t_sync_10_clean_audio_has_no_gap(request: pytest.FixtureRequest, fixture: str) -> None:
    """Catches: false gaps on healthy files (AAC priming, an audio start offset or an edit list are not gaps)."""
    assert abs(audio.audio_gap_s(request.getfixturevalue(fixture))) < 1e-9


def test_t_sync_10_missing_wav_is_regenerated(tmp_path: Path, ingest_settings: Settings) -> None:
    """Catches: a cache that is remembered outside the folder, so a deleted audio.wav is never made again."""
    rec_dir = _one_recording(tmp_path, ingest_settings)
    first = audio.extract_audio(rec_dir)
    names = _names(rec_dir)
    first.unlink()

    again = audio.extract_audio(rec_dir)

    assert again.is_file()
    rate, data = scipy.io.wavfile.read(str(again))
    assert rate == SR
    assert data.ndim == 1 and data.size > 7 * SR  # an 8 s take
    assert _names(rec_dir) == names  # the temporary file is gone


def test_t_sync_10_stereo_source_gives_a_mono_wav(tmp_path: Path, ingest_settings: Settings) -> None:
    """Catches: a stereo (or first-channel-only, or wrong-rate) wav for a two-channel 44.1 kHz AAC source."""
    assert FFMPEG
    media = tmp_path / "media"
    media.mkdir()
    path = media / "stereo.mp4"
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    cmd += ["-f", "lavfi", "-i", "testsrc2=size=64x48:rate=10:duration=2"]
    cmd += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=2"]
    cmd += ["-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100:duration=2"]
    cmd += ["-filter_complex", "[1:a][2:a]amerge=inputs=2[a]", "-map", "0:v", "-map", "[a]"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2", "-shortest", str(path)]
    subprocess.run(cmd, check=True)
    rec_dir = _ingest(path, "camA", ingest_settings)
    manifest = read_manifest(rec_dir / "recording.json", RecordingManifest)
    assert manifest.audio is not None and manifest.audio.channels == 2  # the source really is stereo

    wav = audio.extract_audio(rec_dir)

    rate, data = scipy.io.wavfile.read(str(wav))
    assert rate == 16000
    assert data.ndim == 1
    assert data.dtype == np.int16
    assert abs(data.size / rate - 2.0) < 0.2
    # both channels are mixed in: the left tone (440 Hz) and the right tone (1000 Hz) are both there
    body = data[int(0.3 * rate) :].astype(np.float64)
    spectrum = np.abs(np.fft.rfft(body * np.hanning(body.size)))
    freqs = np.fft.rfftfreq(body.size, 1.0 / rate)
    floor = float(np.median(spectrum))
    for tone_hz in (440.0, 1000.0):
        assert spectrum[np.abs(freqs - tone_hz) < 5.0].max() > 20.0 * floor, f"{tone_hz} Hz is missing"


# --- ffmpeg failure, timeout and cleanup ----------------------------------------------------------------------------


class _FakeFfmpeg:
    """Stands in for ``subprocess.run`` inside ``taiji_ai.io.audio``: writes the temporary output, then fails.

    ``mode`` is ``"fail"`` (return code 1 with an stderr that names a secret path) or ``"timeout"``. A call that is
    only ``-version`` goes to the real function.
    """

    def __init__(self, real_run: object, rec_dir: Path, mode: str) -> None:
        self.real_run = real_run
        self.rec_dir = rec_dir.resolve()
        self.mode = mode
        self.written: list[Path] = []
        self.timeouts: list[object] = []

    def _output(self, cmd: list[str]) -> Path | None:
        for arg in reversed(cmd):
            candidate = Path(str(arg))
            if candidate.name.startswith("audio") and candidate.resolve().parent == self.rec_dir:
                return candidate
        return None

    def __call__(self, cmd: list[str], *args: object, **kwargs: object) -> subprocess.CompletedProcess:
        if "-version" in cmd:
            return self.real_run(cmd, *args, **kwargs)  # type: ignore[operator]
        self.timeouts.append(kwargs.get("timeout"))
        out = self._output(cmd)
        if out is not None:
            out.write_bytes(b"RIFF-partial-output")
            self.written.append(out)
        if self.mode == "timeout":
            raise subprocess.TimeoutExpired(cmd, 1.0)
        text = bool(kwargs.get("text") or kwargs.get("universal_newlines") or kwargs.get("encoding"))
        stderr: str | bytes = FAKE_STDERR if text else FAKE_STDERR.encode()
        stdout: str | bytes = "" if text else b""
        if kwargs.get("check"):
            raise subprocess.CalledProcessError(1, cmd, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(cmd, 1, stdout=stdout, stderr=stderr)


def test_t_sync_10_ffmpeg_failure_leaves_nothing_and_leaks_no_path(
    tmp_path: Path, ingest_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches: a failed ffmpeg run that leaves audio.wav or a temporary file, or puts stderr/paths in the error."""
    rec_dir = _one_recording(tmp_path, ingest_settings)
    names = _names(rec_dir)
    fake = _FakeFfmpeg(subprocess.run, rec_dir, "fail")
    monkeypatch.setattr(audio.subprocess, "run", fake)

    with pytest.raises(audio.AudioError) as info:
        audio.extract_audio(rec_dir)

    assert fake.written, "the fake ffmpeg never saw an output file: the cleanup below proves nothing"
    assert not isinstance(info.value, audio.NoAudioStream)
    message = str(info.value)
    for leak in ("secret", "clip.mp4", str(tmp_path), tmp_path.as_posix()):
        assert leak not in message
    assert not (rec_dir / "audio.wav").exists()
    assert list(rec_dir.glob("audio.tmp*")) == []
    assert not any(p.exists() for p in fake.written)
    assert _names(rec_dir) == names


def test_t_sync_10_ffmpeg_timeout_is_an_audio_error(
    tmp_path: Path, ingest_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches: no timeout at all, a timeout reported as a generic failure, or one that leaves a partial file."""
    rec_dir = _one_recording(tmp_path, ingest_settings)
    names = _names(rec_dir)
    fake = _FakeFfmpeg(subprocess.run, rec_dir, "timeout")
    monkeypatch.setattr(audio.subprocess, "run", fake)

    with pytest.raises(audio.AudioError) as info:
        audio.extract_audio(rec_dir)

    assert fake.timeouts and all(isinstance(t, int | float) and t > 0 for t in fake.timeouts), fake.timeouts
    assert fake.written
    message = str(info.value)
    assert re.search(r"time.?out|timed out|time limit", message, re.IGNORECASE), message
    for leak in ("secret", "clip.mp4", str(tmp_path), tmp_path.as_posix()):
        assert leak not in message
    assert not (rec_dir / "audio.wav").exists()
    assert list(rec_dir.glob("audio.tmp*")) == []
    assert _names(rec_dir) == names


def test_t_sync_10_failed_cleanup_is_logged_and_keeps_the_ffmpeg_error(
    tmp_path: Path, ingest_settings: Settings, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Catches: an unlink error swallowed silently, or one that replaces the AudioError of the ffmpeg failure."""
    rec_dir = _one_recording(tmp_path, ingest_settings)
    fake = _FakeFfmpeg(subprocess.run, rec_dir, "fail")
    monkeypatch.setattr(audio.subprocess, "run", fake)

    def is_temp_audio(p: object) -> bool:
        name = Path(os.fspath(p)).name  # type: ignore[call-overload]
        return name.startswith("audio") and name != "audio.wav"

    real_path_unlink, real_unlink, real_remove = Path.unlink, os.unlink, os.remove

    def path_unlink(self: Path, *args: object, **kwargs: object) -> None:
        if is_temp_audio(self):
            raise PermissionError("simulated: the temporary file is locked")
        real_path_unlink(self, *args, **kwargs)  # type: ignore[arg-type]

    def os_unlink(p: str, *args: object, **kwargs: object) -> None:
        if is_temp_audio(p):
            raise PermissionError("simulated: the temporary file is locked")
        real_unlink(p, *args, **kwargs)  # type: ignore[arg-type]

    def os_remove(p: str, *args: object, **kwargs: object) -> None:
        if is_temp_audio(p):
            raise PermissionError("simulated: the temporary file is locked")
        real_remove(p, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "unlink", path_unlink)
    monkeypatch.setattr(os, "unlink", os_unlink)
    monkeypatch.setattr(os, "remove", os_remove)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(audio.AudioError) as info:
            audio.extract_audio(rec_dir)

    assert fake.written
    # the error the caller sees is the ffmpeg failure, not the failed delete (and it names no file)
    message = str(info.value)
    assert "ffmpeg" in message.lower()
    assert not re.search(r"temp|tmp|permission|locked|unlink|delet|remov", message, re.I), message
    cleanup_warnings = [
        r
        for r in caplog.records
        if r.levelno >= logging.WARNING and re.search(r"temp|tmp|clean|delet|remov|unlink", r.getMessage(), re.I)
    ]
    assert cleanup_warnings, [(r.levelname, r.getMessage()) for r in caplog.records]
    for record in cleanup_warnings:  # IDs only in logs: no file name, no path (AGENTS.md section 6)
        text = record.getMessage()
        assert ".wav" not in text and str(tmp_path) not in text and tmp_path.as_posix() not in text, text


# --- read_wav ------------------------------------------------------------------------------------------------------


READ_WAV_CASES = {
    # dtype: (rate [Hz], written samples, expected float32 values)
    "int16": (
        16000,
        np.array([-32768, -16384, 0, 16384, 32767], dtype=np.int16),
        np.array([-1.0, -0.5, 0.0, 0.5, 32767 / 32768]),
    ),
    "int32": (
        8000,
        np.array([-(2**31), -(2**30), 0, 2**30, 2**31 - 1], dtype=np.int32),
        np.array([-1.0, -0.5, 0.0, 0.5, 1.0]),
    ),
    "uint8": (
        11025,
        np.array([0, 64, 128, 192, 255], dtype=np.uint8),
        np.array([-1.0, -0.5, 0.0, 0.5, 127 / 128]),
    ),
    "float32": (
        22050,
        np.array([-1.0, -0.25, 0.0, 0.5, 1.0], dtype=np.float32),
        np.array([-1.0, -0.25, 0.0, 0.5, 1.0]),
    ),
}


@pytest.mark.parametrize("dtype", list(READ_WAV_CASES))
def test_t_sync_10_read_wav_scales_every_pcm_width_to_float32(tmp_path: Path, dtype: str) -> None:
    """Catches: a wrong scale, a divisor that leaves -1 out of range, a float64 result, or a hard-coded rate."""
    rate, written, expected = READ_WAV_CASES[dtype]
    path = tmp_path / f"{dtype}.wav"
    scipy.io.wavfile.write(str(path), rate, written)

    samples, got_rate = audio.read_wav(path)

    assert got_rate == rate
    assert samples.dtype == np.float32
    assert samples.shape == expected.shape
    np.testing.assert_allclose(samples, expected, rtol=0, atol=1e-4)
    assert float(samples.min()) >= -1.0 and float(samples.max()) <= 1.0


@pytest.mark.parametrize(
    ("dtype", "left", "right", "expected"),
    [
        ("int16", 16384, 0, 0.25),  # 0.5 and 0.0 full scale: the mean is 0.25 (unscaled it would be 8192)
        ("int16", 32767, -32768, -0.5 / 32768),
        ("float32", 0.5, -0.5, 0.0),
        ("float32", 0.8, 0.2, 0.5),
    ],
)
def test_t_sync_10_read_wav_averages_channels_after_scaling(
    tmp_path: Path, dtype: str, left: float, right: float, expected: float
) -> None:
    """Catches: channels averaged BEFORE the scaling (integers become floats and skip it: values like 8192.0)."""
    data = np.tile(np.array([[left, right]], dtype=dtype), (50, 1))
    path = tmp_path / "stereo.wav"
    scipy.io.wavfile.write(str(path), 16000, data)

    samples, rate = audio.read_wav(path)

    assert rate == 16000
    assert samples.dtype == np.float32 and samples.shape == (50,)
    np.testing.assert_allclose(samples, expected, rtol=0, atol=1e-4)
    assert float(np.abs(samples).max()) <= 1.0


@pytest.mark.parametrize(
    ("offset", "value"),
    [(22, 0), (36, 0), (16, 255)],
    ids=["zero_channels", "broken_data_tag", "huge_fmt_chunk"],
)
def test_t_sync_10_read_wav_damaged_header_is_an_audio_error(tmp_path: Path, offset: int, value: int) -> None:
    """Catches: the parser's own errors (UnboundLocalError, ZeroDivisionError) escaping on a damaged header.

    A fuzz of 360 damaged headers made scipy raise those two in 40 cases; the callers (the CLI) catch AudioError only.
    """
    buffer = io.BytesIO()
    scipy.io.wavfile.write(buffer, 16000, (np.arange(200) % 50).astype(np.int16))
    damaged = bytearray(buffer.getvalue())
    damaged[offset] = value
    path = tmp_path / "damaged.wav"
    path.write_bytes(bytes(damaged))

    with pytest.raises(audio.AudioError):
        audio.read_wav(path)


def test_t_sync_10_read_wav_refuses_a_sample_format_it_does_not_handle(tmp_path: Path) -> None:
    """Catches: an unknown sample width (64-bit PCM) taken for audio: unscaled values of 1e17 reaching the filters."""
    payload = (np.arange(100, dtype=np.int64) * 10**15).tobytes()
    fmt = struct.pack("<HHIIHH", 1, 1, 16000, 16000 * 8, 8, 64)  # PCM, mono, 16 kHz, 64 bits per sample
    riff = b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(payload)) + b"WAVE"
    path = tmp_path / "pcm64.wav"
    path.write_bytes(
        riff + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(payload)) + payload
    )
    assert scipy.io.wavfile.read(str(path))[1].dtype == np.int64  # premise: scipy hands it over as int64

    with pytest.raises(audio.AudioError, match="unsupported|sample format"):
        audio.read_wav(path)


def test_t_sync_10_read_wav_missing_file_is_an_audio_error(tmp_path: Path) -> None:
    """Catches: a FileNotFoundError (or no error) for a wav that does not exist."""
    with pytest.raises(audio.AudioError):
        audio.read_wav(tmp_path / "absent.wav")


@pytest.mark.parametrize(
    "content",
    [b"", b"this is not a wav file at all", b"RIFF\x24\x00\x00\x00WAVEfmt "],
    ids=["empty", "text", "truncated_header"],
)
def test_t_sync_10_read_wav_garbage_is_an_audio_error(tmp_path: Path, content: bytes) -> None:
    """Catches: a parser error of scipy (ValueError, struct.error, ...) leaking out of read_wav."""
    path = tmp_path / "broken.wav"
    path.write_bytes(content)

    with pytest.raises(audio.AudioError):
        audio.read_wav(path)


# --- signatures and exception types --------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["extract_audio", "estimate_sync"])
def test_t_sync_10_settings_is_not_a_parameter(tmp_path: Path, name: str) -> None:
    """Catches: the unused ``settings`` argument kept (or hidden behind **kwargs) on the two public functions."""
    if name == "extract_audio":
        fn, args = audio.extract_audio, (tmp_path,)
    else:
        fn, args = audio_sync.estimate_sync, (tmp_path, tmp_path)
    parameters = inspect.signature(fn).parameters

    assert "settings" not in parameters
    assert not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values())
    with pytest.raises(TypeError):
        fn(*args, settings=None)


def test_t_sync_10_exception_hierarchy() -> None:
    """Catches: exceptions that are not an AudioError family, or two refusals that are the same class."""
    sync_error = _exc("SyncError")
    mismatch = _exc("TakeMismatch")
    input_error = _exc("SyncInputError")

    assert issubclass(sync_error, audio.AudioError)
    assert issubclass(mismatch, sync_error)
    assert issubclass(input_error, sync_error)
    assert not issubclass(mismatch, input_error)
    assert not issubclass(input_error, mismatch)


# --- one camera without audio --------------------------------------------------------------------------------------


@pytest.mark.parametrize("lacking", ["camA", "camB"])
def test_t_sync_10_one_camera_without_audio_is_not_found(
    tmp_path: Path, ingest_settings: Settings, lacking: str
) -> None:
    """Catches: an exception, an offset or a drift made up when only one of the two cameras has sound."""
    dir_a, dir_b = _one_audio_pair(tmp_path, ingest_settings, lacking)

    result = audio_sync.estimate_sync(dir_a, dir_b)

    assert result.status == "not_found"
    assert result.not_found_reason == "no_audio"
    assert result.offset_s is None
    assert result.drift is None
    assert result.t_ref_s is None
    assert result.start.found is False and result.start.lag_s is None
    assert result.end.found is False and result.end.lag_s is None


@pytest.mark.parametrize("lacking", ["camA", "camB"])
def test_t_sync_10_one_camera_without_audio_reports_the_real_windows(
    tmp_path: Path, ingest_settings: Settings, lacking: str
) -> None:
    """Catches: the placeholder window (0, 1), windows of B's duration, or numbers made up for windows not searched.

    A lasts 20 s and B 26 s: the windows are A's (section 9.3: 45 % of a take under 60 s, so (0, 9) and (11, 20)).
    """
    duration = 20.0
    dir_a, dir_b = _one_audio_pair(tmp_path, ingest_settings, lacking, duration_s=duration, duration_b_s=26.0)
    manifest_a = read_manifest(dir_a / "recording.json", RecordingManifest)
    assert manifest_a.duration_s is not None and abs(manifest_a.duration_s - duration) < 0.3

    result = audio_sync.estimate_sync(dir_a, dir_b)

    assert result.start.window_a_s == pytest.approx((0.0, 9.0), abs=0.15)
    assert result.end.window_a_s == pytest.approx((11.0, 20.0), abs=0.15)
    for window in (result.start, result.end):
        # nothing was observed in these windows: no peak, no ratio, no lag
        assert window.peak is None and window.peak_ratio is None and window.lag_s is None
        assert window.found is False


def test_t_sync_10_a_take_mismatch_wins_over_a_missing_audio_stream(tmp_path: Path, ingest_settings: Settings) -> None:
    """Catches: the no-audio shortcut taken before the take is checked (a refusal would turn into a quiet not_found)."""
    media = tmp_path / "media"
    media.mkdir()
    file_a = write_camera_file(media / "a.mov", clap_audio(SHORT_A, [6.5, 7.5], seed=1))
    file_b = _write_video_only(media / "b.mov", SHORT_A)
    dir_a = _ingest(file_a, "camA", ingest_settings, take_id="S01-P03-T01")
    dir_b = _ingest(file_b, "camB", ingest_settings, take_id="S01-P03-T02")

    with pytest.raises(_exc("TakeMismatch")):
        audio_sync.estimate_sync(dir_a, dir_b)


def test_t_sync_10_both_cameras_without_audio_are_not_found(tmp_path: Path, ingest_settings: Settings) -> None:
    """Catches: a crash (or an offset) when neither camera has sound."""
    media = tmp_path / "media"
    media.mkdir()
    file_a = _write_video_only(media / "a.mov", SHORT_A)
    file_b = _write_video_only(media / "b.mov", SHORT_A + 1.0)
    dir_a = _ingest(file_a, "camA", ingest_settings)
    dir_b = _ingest(file_b, "camB", ingest_settings)

    result = audio_sync.estimate_sync(dir_a, dir_b)

    assert (result.status, result.not_found_reason) == ("not_found", "no_audio")
    assert result.offset_s is None and result.drift is None and result.t_ref_s is None


# --- refusals of extract_audio ---------------------------------------------------------------------------------------


def test_t_sync_10_extract_audio_refuses_a_missing_source(tmp_path: Path, ingest_settings: Settings) -> None:
    """Catches: a FileNotFoundError or a path in the message when the source video of the recording is gone."""
    rec_dir = _one_recording(tmp_path, ingest_settings)
    source = next(rec_dir.glob("source.*"))
    source.chmod(0o666)
    source.unlink()

    with pytest.raises(audio.AudioError) as info:
        audio.extract_audio(rec_dir)

    assert str(tmp_path) not in str(info.value) and ".mov" not in str(info.value)


def test_t_sync_10_extract_audio_refuses_a_missing_ffmpeg(
    tmp_path: Path, ingest_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches: a crash (or a silent skip) when ffmpeg is not on the PATH."""
    rec_dir = _one_recording(tmp_path, ingest_settings)
    monkeypatch.setattr(audio.shutil, "which", lambda *args, **kwargs: None)

    with pytest.raises(audio.AudioError, match="ffmpeg"):
        audio.extract_audio(rec_dir)

    assert not (rec_dir / "audio.wav").exists()


# --- memory --------------------------------------------------------------------------------------------------------


def test_t_sync_10_ten_minute_take_stays_under_the_memory_limit(
    tmp_path: Path, ingest_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches: an envelope (filters, rectified copies) computed on the whole recording instead of the windows.

    Two checks: the peak memory (calibrated on the reworked code: 141 MB for 10 minutes, 282 MB for 28 minutes, against
    476 MB and about 1.2 GB of the whole-recording version) and the structure, which a half fix would not pass: no
    call of ``envelope`` gets more than the longest window plus the 2 s of filter context on each side.
    """
    tp = make_take_pair(tmp_path / "media", ingest_settings, end_a=600.0, end_b=601.0)
    sizes: list[int] = []
    real_envelope = audio_sync.envelope

    def recording_envelope(x: np.ndarray, *args: object, **kwargs: object) -> np.ndarray:
        sizes.append(int(x.size))
        return real_envelope(x, *args, **kwargs)

    monkeypatch.setattr(audio_sync, "envelope", recording_envelope)

    tracemalloc.start()
    try:
        result = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    peak_mb = peak / (1024 * 1024)

    params = audio_sync.SyncAudioParams()
    # window + search room (range and guard zone) + 2 s of context on each side + a second of rounding
    longest_slice = (params.window_s + params.max_lag_s + params.start_guard_s + 2 * 2.0 + 1.0) * SR
    assert sizes, "the envelope was never computed"
    assert max(sizes) <= longest_slice, f"an envelope of {max(sizes) / SR:.0f} s: the whole recording is filtered"
    assert result.status == "ok"
    assert result.offset_s is not None and result.t_ref_s is not None and result.drift is not None
    assert abs(result.offset_s - tp.truth_offset(result.t_ref_s)) <= 1e-3  # bounded memory must not cost the answer
    assert abs(result.drift) <= 20e-6
    assert peak_mb < MEMORY_LIMIT_MB, f"peak {peak_mb:.0f} MiB >= {MEMORY_LIMIT_MB} MiB"
