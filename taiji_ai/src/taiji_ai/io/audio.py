"""Extract mono 16 kHz audio and read WAV files for audio synchronization (W2 step 1, P2.04).

Audio is extracted with FFmpeg (a list of arguments, never a shell string):
    ffmpeg -i source -map 0:a:0 -vn -ac 1 -ar 16000 -c:a pcm_s16le audio.wav
and cached in ``data/recordings/<recording_id>/audio.wav``. The wav starts at the first audio sample, so a time in the
wav is a time on the audio timeline; ``recording.json`` holds ``audio.start_offset_s`` (audio start minus video start)
to move it to the video timeline. The audio is personal data: it stays inside the recording folder and is deleted with
it.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import av
import numpy as np
import scipy.io.wavfile

from taiji_ai.schemas._base import ManifestError, read_manifest
from taiji_ai.schemas.recording import RecordingManifest

log = logging.getLogger(__name__)

AUDIO_SAMPLE_RATE_HZ = 16000
MAX_AUDIO_GAP_S = 0.002  # [s] a jump of the audio timestamps beyond this is a gap (dropped samples) or an overlap


class AudioError(Exception):
    """An audio extraction or reading operation failed; the message carries IDs only, never paths or ffmpeg's text."""


class NoAudioStream(AudioError):
    """The recording has no audio stream."""


def audio_gap_s(path: Path | str) -> float:
    """Net length [s] of the jumps between audio packets beyond ``MAX_AUDIO_GAP_S`` (positive: samples are missing).

    ffmpeg writes the decoded samples back to back and ignores such a jump, so every time after it in the wav would be
    early by the gap. Packet timestamps are exact (a clean file gives 0), so the check has no tolerance to tune.
    """
    gap, expected = 0.0, None
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        tb = float(stream.time_base)
        for packet in container.demux(stream):
            if packet.pts is None or packet.size == 0:
                continue
            if expected is not None and abs((packet.pts - expected) * tb) > MAX_AUDIO_GAP_S:
                gap += (packet.pts - expected) * tb
            expected = packet.pts + (packet.duration or 0)
    return gap


def extract_audio(recording_dir: Path | str) -> Path:
    """Extract mono 16 kHz audio for a recording, cached as ``audio.wav``; returns its path.

    An existing ``audio.wav`` is returned as it is (it is written atomically, so it is complete).

    Raises:
        AudioError: the folder is invalid, ffmpeg is missing, fails, or times out.
        NoAudioStream: the recording manifest says there is no audio stream.
    """
    rec_path = Path(recording_dir).resolve()
    if not rec_path.is_dir():
        raise AudioError("recording directory does not exist or is not a directory")

    try:
        manifest = read_manifest(rec_path / "recording.json", RecordingManifest)
    except (OSError, ManifestError) as exc:
        raise AudioError("recording manifest is missing or invalid in recording folder") from exc

    rec_id = manifest.recording_id
    if manifest.audio is None:
        raise NoAudioStream(f"recording {rec_id} has no audio stream")

    target = rec_path / "audio.wav"
    if target.is_file():
        return target

    source_path = rec_path / f"source{manifest.source_ext}"
    if not source_path.is_file():
        raise AudioError("source video is missing in recording folder")

    try:
        gap = audio_gap_s(source_path)
    except (OSError, av.error.FFmpegError) as exc:
        raise AudioError("could not read the audio packets of the source video") from exc
    if abs(gap) > MAX_AUDIO_GAP_S:
        # Not repaired: the time of a clap after the gap would be wrong by the gap, and the sync would say ok.
        raise AudioError(
            f"the audio track of recording {rec_id} has {gap * 1000:.0f} ms of dropped or repeated samples: "
            "its times cannot be trusted, so a sync by sound is refused"
        )

    ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        raise AudioError("ffmpeg is not available on PATH")

    tmp_target = rec_path / f"audio.tmp-{uuid.uuid4().hex}.wav"
    cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(AUDIO_SAMPLE_RATE_HZ),
        "-c:a",
        "pcm_s16le",
        str(tmp_target),
    ]
    timeout_s = max(60.0, (manifest.duration_s or 60.0) * 2.0)
    try:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
        except subprocess.TimeoutExpired:
            raise AudioError(f"ffmpeg timed out after {timeout_s:.0f} s while extracting the audio") from None
        if res.returncode != 0:
            log.error("ffmpeg failed with code %d while extracting the audio of recording %s", res.returncode, rec_id)
            raise AudioError("ffmpeg failed to extract audio from the source video")
        os.replace(tmp_target, target)
    except OSError as exc:
        raise AudioError("could not extract the audio (ffmpeg could not run, or no disk space or permission)") from exc
    finally:
        try:
            tmp_target.unlink(missing_ok=True)
        except OSError:
            log.warning("could not remove the temporary audio file of recording %s", rec_id)

    log.info("extracted audio.wav for recording %s", rec_id)
    return target


def read_wav(path: Path | str) -> tuple[np.ndarray, int]:
    """Read a WAV file into a 1-D float32 array in [-1.0, 1.0] (channels averaged) and its sample rate [Hz].

    Raises:
        AudioError: the file does not exist, is not a readable WAV, or has a sample format that is not handled.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise AudioError("audio file does not exist")
    try:
        sr, data = scipy.io.wavfile.read(file_path)
    except Exception as exc:  # noqa: BLE001 - scipy's parser also lets UnboundLocalError, ZeroDivisionError, ... through
        # on a damaged header (a fuzz of 360 headers: 40 of them); whatever it raises, the caller sees an AudioError
        raise AudioError("could not read the WAV file") from exc

    # Scale by the sample format first, then average the channels (averaging first turns integers into floats and
    # would skip the scaling).
    if data.dtype == np.int16:
        samples = data.astype(np.float32)
        samples *= np.float32(1.0 / 32768.0)
    elif data.dtype == np.int32:
        samples = data.astype(np.float32)
        samples *= np.float32(1.0 / 2147483648.0)
    elif data.dtype == np.uint8:
        samples = (data.astype(np.float32) - 128.0) * np.float32(1.0 / 128.0)
    elif np.issubdtype(data.dtype, np.floating):
        samples = data.astype(np.float32)
    else:
        raise AudioError(f"unsupported WAV sample format {data.dtype}")

    if samples.ndim > 1:
        samples = np.mean(samples, axis=1, dtype=np.float32)

    return samples, int(sr)
