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
