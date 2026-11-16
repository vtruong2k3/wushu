"""T-SYNC-08: statuses and plausibility of the two-camera audio sync (P2.04 rework, BUG-0058, BUG-0061).

Every take is made by ``helpers.sync_media.make_take_pair`` (two cameras, claps at known global times, known truth),
except the two inputs that the helper cannot make (identical audio on both cameras, files without an audio stream).

Contract under test (``Docs/tasks/P2.04.md`` section 9.3):

* the end window is searched only when the start was found, around the position that the start offset predicts, within
  ``end_margin_s + max_drift * dt``; a drift beyond ``max_drift`` (500e-6) is never accepted: the end window is
  reported ``found = false`` (lag ``None``, the measured peak kept) and the status is ``start_only``;
* ``start_only`` keeps the offset and has no drift, ``not_found`` has neither;
* a correlation peak is clipped to ``[0, 1]`` (identical audio rounds to 1.0000000000000002, which the schema refuses);
* a recording without audio still reports the windows that would have been searched, from the container duration.

New names of the reworked code are only referenced inside the test bodies, so the file collects on the old code.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from helpers.sync_media import FFMPEG, TakePair, clap_audio, make_take_pair, write_camera_file
from taiji_ai.config import Settings
from taiji_ai.io import audio, audio_sync
from taiji_ai.io.ingest import ingest_recording

pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not available")

END_A = 120.0  # A records [0, 120] s
END_B = 121.0  # B records [0.5, 121] s (start_b default of the helper)
MAX_DRIFT = 500e-6  # dimensionless: the plausibility limit of section 9.3 (max_drift, 500 ppm)


def _take(tmp_path: Path, settings: Settings, **kwargs: Any) -> TakePair:
    """A 120 s take, B starting 0.5 s late and stopping 1 s after A, unless the caller says otherwise."""
    return make_take_pair(tmp_path / "media", settings, end_a=END_A, end_b=END_B, **kwargs)


def _ingest(path: Path, camera_id: str, settings: Settings) -> Path:
    """Ingest one file as a camera of take S01-P03-T01 (the meta of the helper) and return the recording folder."""
    meta = {"participant_id": "P03", "session_id": "S01", "take_id": "S01-P03-T01", "camera_id": camera_id}
    rec = ingest_recording(path, meta, settings)
    return settings.data_dir / "recordings" / rec.manifest.recording_id


def test_t_sync_08_start_only_when_the_end_has_no_claps(tmp_path: Path, ingest_settings: Settings) -> None:
    """Catches: an end window "found" in noise, a lost start offset, or a drift made up (0) for a missing end."""
    tp = _take(tmp_path, ingest_settings, end_pair=False)

    res = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    assert res.status == "start_only"
    assert res.not_found_reason is None
    assert res.drift is None
    assert res.t_ref_s is not None
    assert res.offset_s is not None
    assert abs(res.offset_s - tp.truth_offset(res.t_ref_s)) <= 0.001
    assert res.start.found is True
    assert res.end.found is False
    assert res.end.lag_s is None


def test_t_sync_08_not_found_when_only_the_end_has_claps(tmp_path: Path, ingest_settings: Settings) -> None:
    """Catches: an end window searched (and found) without a start offset to predict it, or an offset made up."""
    tp = _take(tmp_path, ingest_settings, start_pair=False)

    res = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    assert res.status == "not_found"
    assert res.not_found_reason == "clap_not_found"
    assert res.offset_s is None
    assert res.drift is None
    assert res.t_ref_s is None
    assert res.start.found is False
    assert res.end.found is False
    assert res.end.lag_s is None


@pytest.mark.parametrize(
    "drift",
    [5000e-6, -5000e-6, 600e-6, -600e-6],
    ids=["plus5000ppm", "minus5000ppm", "plus600ppm", "minus600ppm"],
)
def test_t_sync_08_drift_beyond_the_limit_is_start_only(
    tmp_path: Path, ingest_settings: Settings, drift: float
) -> None:
    """Catches: a drift beyond 500 ppm accepted as ``ok`` (either sign: ``abs`` forgotten), a limit set too high
    (600 ppm is just beyond it), or the measured end peak and ratio thrown away."""
    tp = _take(tmp_path, ingest_settings, drift=drift)  # at 5000 ppm the end claps move 0.53 s

    res = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    assert res.status == "start_only"
    assert res.not_found_reason is None
    assert res.drift is None
    assert res.end.found is False
    assert res.end.lag_s is None
    assert res.end.peak is not None  # the measured values stay in the record (section 9.3)
    assert res.end.peak_ratio is not None
    # the start offset is kept and right at t_ref_s (at the window centre, 15 s, the truth would be 40 ms away); 5 ms
    # because 5000 ppm times half the clap pair gap (0.5 s) is 2.5 ms of position uncertainty
    assert res.offset_s is not None
    assert res.t_ref_s is not None
    assert abs(res.offset_s - tp.truth_offset(res.t_ref_s)) <= 0.005


@pytest.mark.parametrize("true_drift", [400e-6, 480e-6, -480e-6], ids=["plus400ppm", "plus480ppm", "minus480ppm"])
def test_t_sync_08_drift_below_the_limit_is_ok_with_the_right_size(
    tmp_path: Path, ingest_settings: Settings, true_drift: float
) -> None:
    """Catches: a plausibility limit that is too tight (rejecting 480 ppm) or a drift that is 18 % off (centres)."""
    tp = _take(tmp_path, ingest_settings, drift=true_drift)

    res = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    assert res.status == "ok"
    assert res.drift is not None
    assert abs(res.drift - true_drift) / abs(true_drift) <= 0.10


def test_t_sync_08_the_search_range_includes_the_drift_allowance(tmp_path: Path, ingest_settings: Settings) -> None:
    """Catches: a search range that is only the fixed margin: the range is ``end_margin_s + max_drift * dt``.

    The limit is raised to 2 % and the take drifts by 1 %: the end claps move 1.06 s, which the fixed margin (0.3 s)
    does not reach; only the drift allowance (2 % of the 98 s between the windows, 1.96 s) does. (A margin of 0 would
    leave a range narrower than the 0.5 s exclusion radius, where no second peak can be measured: not found.)
    """
    true_drift = 10000e-6
    tp = _take(tmp_path, ingest_settings, drift=true_drift)
    params = audio_sync.SyncAudioParams(end_margin_s=0.3, max_drift=0.02)

    res = audio_sync.estimate_sync(tp.dir_a, tp.dir_b, params=params)

    assert res.status == "ok"
    assert res.drift is not None and abs(res.drift - true_drift) / true_drift <= 0.10


@pytest.mark.parametrize(
    "drift",
    [3000e-6, -3000e-6, 5000e-6, -5000e-6, 9091e-6],
    ids=["plus3000ppm", "minus3000ppm", "plus5000ppm", "minus5000ppm", "plus9091ppm"],
)
def test_t_sync_08_a_wrong_lag_is_never_ok(tmp_path: Path, ingest_settings: Settings, drift: float) -> None:
    """Catches: an end lag that is wrong (the other clap of the pair, 1 s away) reported as ``ok``.

    9091 ppm is the nasty case: over the 106 s between the clap pairs B's end claps move 0.97 s, so B's first end clap
    lies on A's second end clap. With a search margin that is narrower than the clap pair gap, a one-clap match (peak
    about 0.5, against 0.98 or more for a two-clap match) is found inside the plausible band with a drift of only
    -340 ppm, which the drift limit cannot refuse. The margin of section 9.3 (``end_margin_s`` 3.5 s) is wider than the
    gap, so the true two-clap match is the best peak, and the drift limit rejects it. Any status but ``ok`` is fine.
    """
    tp = _take(tmp_path, ingest_settings, drift=drift)

    res = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    if res.status != "ok":
        assert res.drift is None  # no drift (and never a made-up 0) without a trusted end
        return
    assert res.drift is not None and res.offset_s is not None and res.t_ref_s is not None
    assert abs(res.drift) <= MAX_DRIFT
    t_a = tp.a_video_time_of(tp.clap_times_global[2])  # the first end clap, on A's video timeline
    true_t_b = t_a + tp.truth_offset(t_a)
    predicted_t_b = t_a + res.offset_s + res.drift * (t_a - res.t_ref_s)
    assert abs(predicted_t_b - true_t_b) <= 0.002


@pytest.mark.parametrize("seed", [1, 6, 7, 8])
def test_t_sync_08_identical_audio_is_ok_without_a_schema_error(
    tmp_path: Path, ingest_settings: Settings, seed: int
) -> None:
    """Catches: a correlation above 1 by rounding reaching the schema (peak <= 1) and failing the whole sync.

    Whether the rounding of an exact match lands above 1 depends on the noise and on the arithmetic, so four noise
    seeds are tried. This is the end-to-end smoke test; the clipping itself is guarded at the matcher level by
    ``test_t_sync_09_identical_arrays_peak_is_at_most_one`` (40 seeds).
    """
    media = tmp_path / "media"
    media.mkdir()
    samples = clap_audio(20.0, [6.0, 7.0, 13.0, 14.0], seed=seed)
    # the video of B differs (12 fps), only so that the content hash differs: ingest refuses the same file twice
    file_a = write_camera_file(media / "a.mov", samples, video_fps=10)
    file_b = write_camera_file(media / "b.mov", samples, video_fps=12)
    dir_a = _ingest(file_a, "camA", ingest_settings)
    dir_b = _ingest(file_b, "camB", ingest_settings)
    # premise of the test: the sound of the two cameras is sample for sample the same
    wav_a, sr_a = audio.read_wav(audio.extract_audio(dir_a))
    wav_b, sr_b = audio.read_wav(audio.extract_audio(dir_b))
    assert sr_a == sr_b
    assert np.array_equal(wav_a, wav_b)

    res = audio_sync.estimate_sync(dir_a, dir_b)

    assert res.status == "ok"
    assert res.offset_s is not None
    assert abs(res.offset_s) <= 0.001
    assert res.drift is not None
    assert abs(res.drift) <= 10e-6
    for window in (res.start, res.end):
        assert window.found is True
        assert window.peak is not None
        assert 0.99 < window.peak <= 1.0  # an exact match: found for the right reason, and never above 1


def test_t_sync_08_no_audio_reports_the_windows_that_would_have_been_searched(
    tmp_path: Path, ingest_settings: Settings
) -> None:
    """Catches: the placeholder window (0, 1) of the old code, or a drift/offset made up for a take without sound."""
    media = tmp_path / "media"
    media.mkdir()
    dirs = []
    for name, camera_id in (("a", "camA"), ("b", "camB")):
        path = media / f"{name}.mov"
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi"]
        cmd += ["-i", "testsrc2=size=64x48:rate=10:duration=120", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        # a comment makes the two files differ in content (ingest refuses the same file twice)
        cmd += ["-metadata", f"comment=cam-{name}", str(path)]
        subprocess.run(cmd, check=True)
        dirs.append(_ingest(path, camera_id, ingest_settings))

    res = audio_sync.estimate_sync(dirs[0], dirs[1])

    assert res.status == "not_found"
    assert res.not_found_reason == "no_audio"
    assert res.offset_s is None
    assert res.drift is None
    assert res.t_ref_s is None
    assert res.start.found is False
    assert res.end.found is False
    # section 9.3: windows of 30 s at both ends of the 120 s take (the old placeholder (0, 1) fails here too)
    assert res.start.window_a_s == pytest.approx((0.0, 30.0), abs=0.1)
    assert res.end.window_a_s == pytest.approx((90.0, 120.0), abs=0.1)
    # derived from the container duration: the start window opens the take, the end window closes it
    assert res.start.window_a_s[0] <= 0.5
    assert res.end.window_a_s[1] >= 119.5
