"""T-SYNC-04g..04j, 04m, 04n: the mapping, the frame interval, the search margin, the window and the refusals of
``validate_sync`` / ``brightness_series`` (P2.05 rework, BUG-0067, BUG-0068).

The audio result is the real one of a fixture (``helpers.flash_media``), changed with ``dataclasses.replace`` where a
test needs a given mapping; the flash video is real and encoded.
"""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from helpers.flash_media import PAIRS_A, make_flash_take
from helpers.sync_media import FFMPEG
from taiji_ai.config import Settings
from taiji_ai.io import flash as flash_module
from taiji_ai.io.audio_sync import estimate_sync
from taiji_ai.io.flash import FlashError, brightness_series, find_flash_onsets, validate_sync

pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not available")

DELTA_S = 0.5


def _take(tmp_path: Path, settings: Settings, **kwargs):
    dir_a, dir_b = make_flash_take(tmp_path / "take", settings, **kwargs)
    audio = estimate_sync(dir_a, dir_b)
    assert audio.status == "ok", f"the audio sync of the fixture must be ok, got {audio.status}"
    return dir_a, dir_b, audio


def test_t_sync_04g_a_mapping_with_drift_is_used_at_both_pairs(tmp_path: Path, ingest_settings: Settings):
    """B's flashes sit where offset 0.5 s, drift 3 % and t_ref 2.5 s put them; ignoring either misses by frames."""
    offset, drift, t_ref = DELTA_S, 0.03, 2.5
    flashes_b = tuple(t + offset + drift * (t - t_ref) for t in PAIRS_A)
    dir_a, dir_b, audio = _take(tmp_path, ingest_settings, flashes_b=flashes_b)
    mapping = replace(audio, offset_s=offset, drift=drift, t_ref_s=t_ref)

    validation = validate_sync(mapping, dir_a, dir_b)

    assert validation.method == "flash"
    assert validation.residual_frames is not None and validation.residual_frames <= 1.0, validation.residual_ms


def test_t_sync_04h_the_order_of_the_two_folders_does_not_matter(tmp_path: Path, ingest_settings: Settings):
    dir_a, dir_b, audio = _take(tmp_path, ingest_settings)

    normal = validate_sync(audio, dir_a, dir_b)
    swapped = validate_sync(audio, dir_b, dir_a)

    assert normal.method == swapped.method == "flash"
    assert normal.residual_ms is not None and swapped.residual_ms is not None
    assert swapped.residual_ms == pytest.approx(normal.residual_ms)
    assert swapped.flash_a_s == normal.flash_a_s and swapped.flash_b_s == normal.flash_b_s


def test_t_sync_04i_the_residual_is_in_frames_of_the_slower_camera(tmp_path: Path, ingest_settings: Settings):
    """A films at 30 fps, B at 15 fps: the frame is B's 66.7 ms, and a right mapping is within one such frame."""
    dir_a, dir_b, audio = _take(tmp_path, ingest_settings, fps_b=15)

    validation = validate_sync(audio, dir_a, dir_b)

    assert validation.method == "flash"
    assert validation.frame_dt_s == pytest.approx(1 / 15, abs=0.002)
    assert validation.residual_ms is not None and validation.residual_frames is not None
    assert validation.residual_frames == pytest.approx(validation.residual_ms / 1000.0 / validation.frame_dt_s)
    assert validation.residual_frames <= 1.0


def test_t_sync_04j_a_lag_error_beyond_the_pair_gap_is_measured(tmp_path: Path, ingest_settings: Settings):
    """The mapping is 3 s wrong: B's flashes are 3 s from where it puts them, inside the search margin (2 s on each side
    of the window): a residual of about 3000 ms, not 'not found'."""
    dir_a, dir_b, audio = _take(tmp_path, ingest_settings)
    assert audio.offset_s is not None
    wrong = replace(audio, offset_s=audio.offset_s + 3.0)

    validation = validate_sync(wrong, dir_a, dir_b)

    assert validation.method == "flash"
    assert validation.residual_start_ms is not None and validation.residual_end_ms is not None
    assert validation.residual_start_ms == pytest.approx(3000.0, abs=70.0)
    assert validation.residual_end_ms == pytest.approx(3000.0, abs=70.0)


def test_t_sync_04m_a_window_of_a_long_clip_gives_only_the_window_at_exact_frames(tmp_path: Path):
    """40 s clip, flashes at 5, 12 and 30 s: the window 10..20 s shows only the flash at 12 s, at its exact frame."""
    video = tmp_path / "long.mp4"
    boxes = ",".join(f"drawbox=enable='between(n,{n},{n + 14})':color=white:t=fill" for n in (150, 360, 900))
    source = "testsrc2=size=64x48:rate=30:duration=40"
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", source]
    cmd += ["-vf", boxes, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(video)]
    subprocess.run(cmd, check=True)

    t, luma = brightness_series(video, t0=10.0, t1=20.0)

    assert t.min() >= 10.0 - 1e-6 and t.max() <= 20.0 + 1e-6
    assert np.all(np.diff(t) > 0)
    onsets = find_flash_onsets(t, luma)
    assert len(onsets) == 1 and abs(onsets[0] - 12.0) < 1e-3, onsets


def test_t_sync_04n_an_audio_result_that_is_not_ok_gives_no_validation(tmp_path: Path, ingest_settings: Settings):
    dir_a, dir_b, audio = _take(tmp_path, ingest_settings)
    not_ok = replace(audio, status="not_found", offset_s=None, drift=None, t_ref_s=None)

    validation = validate_sync(not_ok, dir_a, dir_b)

    assert validation.method == "none"
    assert validation.residual_ms is None and validation.residual_frames is None
    assert validation.flash_a_s == () and validation.flash_b_s == ()


def test_t_sync_04n_the_recordings_must_be_those_of_the_audio_result(tmp_path: Path, ingest_settings: Settings):
    """BUG-0067: recordings other than those of the audio result are refused, whatever the audio status."""
    dir_a, dir_b, audio = _take(tmp_path, ingest_settings)
    other = replace(audio, recording_id_a="00000000-0000-4000-8000-000000000000")

    with pytest.raises(FlashError, match="not those of the audio"):
        validate_sync(other, dir_a, dir_b)
    with pytest.raises(FlashError, match="not those of the audio"):
        validate_sync(replace(other, status="not_found", offset_s=None, drift=None), dir_a, dir_b)


def test_t_sync_04n_a_manifest_without_a_frame_interval_is_refused(
    tmp_path: Path, ingest_settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    """BUG-0067: no made-up 30 fps: a recording without ``median_dt_s`` cannot give a residual in frames."""
    dir_a, dir_b, audio = _take(tmp_path, ingest_settings)
    real_read = flash_module.read_manifest

    def read_without_interval(path, model):
        return real_read(path, model).model_copy(update={"median_dt_s": None})

    monkeypatch.setattr(flash_module, "read_manifest", read_without_interval)

    with pytest.raises(FlashError, match="frame interval"):
        validate_sync(audio, dir_a, dir_b)


def test_t_sync_04n_a_mapping_without_a_reference_time_gives_no_validation(tmp_path: Path, ingest_settings: Settings):
    """BUG-0067: a missing ``t_ref_s`` is not turned into 0.0; the mapping is unusable and the method is none."""
    dir_a, dir_b, audio = _take(tmp_path, ingest_settings)

    validation = validate_sync(replace(audio, t_ref_s=None), dir_a, dir_b)

    assert validation.method == "none" and validation.residual_ms is None
