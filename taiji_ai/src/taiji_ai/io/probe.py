"""ffprobe wrapper: container/stream metadata for ingest (W1)."""

from __future__ import annotations

import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from pydantic import BaseModel


class ProbeError(RuntimeError):
    pass


class NoVideoStreamError(ProbeError):
    """The file opens but has no video stream (for example an audio-only file)."""


class AudioMeta(BaseModel):
    codec: str
    sample_rate: int  # Hz
    channels: int
    start_time_s: float  # on the container clock, like ``VideoMeta.start_time_s``


class VideoMeta(BaseModel):
    path: str
    format_name: str  # ffprobe format_name, e.g. "mov,mp4,m4a,3gp,3g2,mj2"
    codec: str
    width: int
    height: int
    time_base: str  # e.g. "1/90000"
    r_frame_rate: float  # container "base" rate
    avg_frame_rate: float
    duration_s: float | None
    nb_frames: int | None
    rotation: int  # degrees from the display matrix, normalised to {0, 90, 180, 270}
    has_audio: bool
    audio: AudioMeta | None  # the first audio stream, if any
    start_time_s: float


def _rate(s: str | None) -> float:
    if not s or s in ("0/0", "N/A"):
        return 0.0
    return float(Fraction(s))


def _rotation(stream: dict) -> int:
    rot = 0.0
    for sd in stream.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = float(sd["rotation"])
            break
    else:
        tag = (stream.get("tags") or {}).get("rotate")
        if tag is not None:
            rot = -float(tag)  # legacy tag uses the opposite sign of the display matrix
    return int(round(rot)) % 360


def ffprobe_json(path: str | Path) -> dict:
    exe = shutil.which("ffprobe")
    if exe is None:
        raise ProbeError("ffprobe not found on PATH")
    cmd = [exe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise ProbeError(f"ffprobe failed for {path}: {res.stderr.strip()[:300]}")
    return json.loads(res.stdout)


def probe_video(path: str | Path) -> VideoMeta:
    info = ffprobe_json(path)
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise NoVideoStreamError(f"no video stream in {path}")
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    audio = (
        AudioMeta(
            codec=audio_stream.get("codec_name", "unknown"),
            sample_rate=int(audio_stream.get("sample_rate") or 0),
            channels=int(audio_stream.get("channels") or 0),
            start_time_s=float(audio_stream.get("start_time") or 0.0),
        )
        if audio_stream is not None
        else None
    )
    fmt = info.get("format", {})
    dur = video.get("duration") or fmt.get("duration")
    nb = video.get("nb_frames")
    return VideoMeta(
        path=str(path),
        format_name=fmt.get("format_name", "unknown"),
        codec=video.get("codec_name", "unknown"),
        width=int(video["width"]),
        height=int(video["height"]),
        time_base=video.get("time_base", "0/0"),
        r_frame_rate=_rate(video.get("r_frame_rate")),
        avg_frame_rate=_rate(video.get("avg_frame_rate")),
        duration_s=float(dur) if dur not in (None, "N/A") else None,
        nb_frames=int(nb) if nb not in (None, "N/A") else None,
        rotation=_rotation(video),
        has_audio=audio is not None,
        audio=audio,
        start_time_s=float(video.get("start_time") or 0.0),
    )
