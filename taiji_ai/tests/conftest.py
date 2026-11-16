"""Shared fixtures: small synthetic videos generated with the FFmpeg CLI; logging-state isolation (BUG-0016)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import pytest

from taiji_ai.logs import _TAIJI_HANDLER_ATTR

FFMPEG = shutil.which("ffmpeg")

_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")


def _logging_state() -> tuple:
    """Global logging state a test must not change: root level, our handlers, uvicorn loggers."""
    root = logging.getLogger()
    ours = tuple(id(h) for h in root.handlers if getattr(h, _TAIJI_HANDLER_ATTR, False))
    uvicorn = tuple(
        (name, lg.level, tuple(id(h) for h in lg.handlers), lg.propagate)
        for name in _UVICORN_LOGGERS
        for lg in [logging.getLogger(name)]
    )
    return root.level, ours, uvicorn


@pytest.fixture(autouse=True)
def _logging_state_guard():
    """BUG-0016: fail (at teardown) any test that leaves global logging state changed. Use ``clean_logging``."""
    before = _logging_state()
    yield
    after = _logging_state()
    assert after == before, (
        f"test changed global logging state (root level, taiji handlers or uvicorn loggers): {before} -> {after}; "
        "use the clean_logging fixture"
    )


@pytest.fixture
def clean_logging():
    """Run a test with no taiji handler on the root logger; restore root and uvicorn logger state afterwards.

    Handlers added during the test are removed and closed; handlers that existed before are put back unchanged.
    """
    root = logging.getLogger()
    old_handlers = list(root.handlers)
    old_level = root.level
    saved_uvicorn = {name: (lg.level, list(lg.handlers), lg.propagate) for name in _UVICORN_LOGGERS
                     for lg in [logging.getLogger(name)]}  # fmt: skip
    detached = [h for h in old_handlers if getattr(h, _TAIJI_HANDLER_ATTR, False)]
    for h in detached:
        root.removeHandler(h)
    try:
        yield
    finally:
        for h in list(root.handlers):
            if h not in old_handlers:
                root.removeHandler(h)
                h.close()
        for h in detached:
            root.addHandler(h)
        root.setLevel(old_level)
        for name, (level, handlers, propagate) in saved_uvicorn.items():
            lg = logging.getLogger(name)
            lg.setLevel(level)
            lg.handlers = handlers
            lg.propagate = propagate
        logging.captureWarnings(False)


def _ffmpeg(*args: str) -> None:
    assert FFMPEG, "ffmpeg not on PATH"
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="session")
def video_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not FFMPEG:
        pytest.skip("ffmpeg not available")
    return tmp_path_factory.mktemp("videos")


@pytest.fixture(scope="session")
def cfr_video(video_dir: Path) -> Path:
    """2 s, 30 fps constant frame rate, 320x240, with a 1 kHz audio track."""
    out = video_dir / "cfr.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "15", "-c:a", "aac", "-shortest", str(out),
    )  # fmt: skip
    return out


@pytest.fixture(scope="session")
def vfr_video(video_dir: Path) -> Path:
    """First second at 30 fps, then every 3rd frame kept (10 fps) -> variable frame rate."""
    out = video_dir / "vfr.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=2",
        "-vf", r"select='lt(n\,30)+not(mod(n\,3))'",
        "-fps_mode", "vfr", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out),
    )  # fmt: skip
    return out


@pytest.fixture(scope="session")
def rotated_video(video_dir: Path, cfr_video: Path) -> Path:
    """Same stream as cfr_video with display-matrix rotation metadata (90° CCW)."""
    out = video_dir / "rot90.mp4"
    _ffmpeg("-display_rotation", "90", "-i", str(cfr_video), "-c", "copy", str(out))
    return out


@pytest.fixture(scope="session")
def one_frame_video(video_dir: Path) -> Path:
    """A valid video with a single frame: it has no frame interval at all."""
    out = video_dir / "one_frame.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30",
        "-frames:v", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out),
    )  # fmt: skip
    return out


@pytest.fixture(scope="session")
def offset_video(video_dir: Path) -> Path:
    """Like cfr_video but the video starts at 5.0 s (start_pts 76800 at 1/15360) and the audio about 0.5 s later."""
    out = video_dir / "offset.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=2",
        "-itsoffset", "0.5", "-f", "lavfi", "-i", "sine=frequency=1000:duration=2",
        "-output_ts_offset", "5",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "15", "-c:a", "aac", "-shortest", str(out),
    )  # fmt: skip
    return out


@pytest.fixture
def ingest_settings(tmp_path: Path):
    """Settings with an empty data folder, a migrated database and one registered participant ``P03`` (invented)."""
    from taiji_ai.config import Settings
    from taiji_ai.store.db import connect
    from taiji_ai.store.participants import register_participant

    settings = Settings(data_dir=tmp_path / "data")
    conn = connect(settings.db_path, settings.migrations_dir)
    try:
        register_participant(
            conn,
            "P03",
            "CONSENT-2026-011",
            analysis=True,
            train=False,
            share=False,
            retention_until=None,
            actor="cli:O",
        )
    finally:
        conn.close()
    return settings


def _coarse_cfr(video_dir: Path, name: str, rate: str) -> Path:
    """4 s of constant frame rate at the given rate, 160x120, video time base 1/1000 (BUG-0046), no audio."""
    out = video_dir / name
    _ffmpeg(
        "-f", "lavfi", "-i", f"testsrc2=size=160x120:rate={rate}:duration=4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-video_track_timescale", "1000", "-an", str(out),
    )  # fmt: skip
    return out


@pytest.fixture(scope="session")
def coarse_cfr_30(video_dir: Path) -> Path:
    """30 fps at time base 1/1000: the frame intervals are 33 or 34 ms, yet the video is constant frame rate."""
    return _coarse_cfr(video_dir, "coarse30.mp4", "30")


@pytest.fixture(scope="session")
def coarse_cfr_2997(video_dir: Path) -> Path:
    """29.97 fps (30000/1001) at time base 1/1000."""
    return _coarse_cfr(video_dir, "coarse2997.mp4", "30000/1001")


@pytest.fixture(scope="session")
def dropped_frame_video(video_dir: Path) -> Path:
    """10 s at 30 fps with frame 150 removed: 299 frames, one interval twice as long as the others."""
    out = video_dir / "dropped.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=30:duration=10",
        "-vf", r"select='not(eq(n\,150))'", "-fps_mode", "vfr",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out),
    )  # fmt: skip
    return out


@pytest.fixture(scope="session")
def audio_only_video(video_dir: Path) -> Path:
    """An MP4 with an audio track and no video stream."""
    out = video_dir / "audio_only.mp4"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=1000:duration=2", "-c:a", "aac", str(out))
    return out


@pytest.fixture(scope="session")
def truncated_video(video_dir: Path, cfr_video: Path) -> Path:
    """The first 600 bytes of a real MP4: the index (moov atom) is missing, so it cannot be read."""
    out = video_dir / "truncated.mp4"
    out.write_bytes(cfr_video.read_bytes()[:600])
    return out


@pytest.fixture(scope="session")
def empty_video(video_dir: Path) -> Path:
    out = video_dir / "empty.mp4"
    out.write_bytes(b"")
    return out


@pytest.fixture(scope="session")
def ffmpeg_first_frame():
    """Decode the first frame with ffmpeg's own autorotation, as BGR ndarray."""
    import numpy as np

    from taiji_ai.io.probe import probe_video

    def _decode(path: Path) -> np.ndarray:
        meta = probe_video(path)
        w, h = (meta.height, meta.width) if meta.rotation in (90, 270) else (meta.width, meta.height)
        res = subprocess.run(
            [FFMPEG, "-v", "error", "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
            check=True, capture_output=True,
        )  # fmt: skip
        return np.frombuffer(res.stdout, np.uint8).reshape(h, w, 3)

    return _decode
