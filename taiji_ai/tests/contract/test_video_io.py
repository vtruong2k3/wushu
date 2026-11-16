from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest

from taiji_ai.io.frames import is_vfr, iter_frames, scan_pts, scan_pts_ticks, vfr_verdict
from taiji_ai.io.probe import NoVideoStreamError, ProbeError, probe_video


def test_probe_cfr(cfr_video):
    m = probe_video(cfr_video)
    assert (m.width, m.height) == (320, 240)
    assert m.codec == "h264"
    assert m.has_audio
    assert m.rotation == 0
    assert m.avg_frame_rate == pytest.approx(30, abs=0.01)


def test_scan_pts_cfr_is_regular(cfr_video):
    t, tb = scan_pts(cfr_video)
    assert len(t) == 60
    assert t[0] == pytest.approx(0.0, abs=1e-6)
    assert np.all(np.diff(t) > 0)
    assert not is_vfr(t, tb)
    assert np.median(np.diff(t)) == pytest.approx(1 / 30, rel=1e-3)


def test_scan_pts_detects_vfr(vfr_video):
    t, tb = scan_pts(vfr_video)
    assert len(t) == 30 + 10  # 30 frames in the 1st second, every 3rd frame in the 2nd
    assert is_vfr(t, tb)
    assert vfr_verdict(scan_pts_ticks(vfr_video).pts).vfr is True
    dt = np.diff(t)
    assert dt[:29] == pytest.approx(1 / 30, rel=1e-2)
    assert dt[-5:] == pytest.approx(3 / 30, rel=1e-2)


def test_scan_pts_ticks_gives_integer_timestamps_and_the_time_base(cfr_video):
    scan = scan_pts_ticks(cfr_video)
    assert scan.pts.dtype == np.int64 and len(scan.pts) == 60
    assert scan.time_base == Fraction(1, 15360) and scan.start_pts == 0
    assert np.all(np.diff(scan.pts) == 512)  # 15360 ticks per second / 30 fps
    t, tb = scan_pts(cfr_video)
    assert np.array_equal(scan.t_sec, t) and float(scan.time_base) == tb  # scan_pts keeps its interface


@pytest.mark.parametrize("fixture", ["coarse_cfr_30", "coarse_cfr_2997"])
def test_t_io_12_constant_frame_rate_with_a_coarse_time_base_is_not_vfr(request, fixture):
    """BUG-0046: at 1 ms ticks a constant 30 fps video has intervals of 33 and 34 ms."""
    path = request.getfixturevalue(fixture)
    scan = scan_pts_ticks(path)
    assert scan.time_base == Fraction(1, 1000)
    dt = np.diff(scan.pts)
    assert set(np.unique(dt)) <= {33, 34} and len(set(np.unique(dt))) == 2
    assert np.std(dt) / np.median(dt) > 0.01  # the old rule (spread in seconds) would have said VFR
    t, tb = scan_pts(path)
    assert not is_vfr(t, tb)
    assert vfr_verdict(scan.pts).vfr is False


def test_t_io_12_a_single_dropped_frame_is_not_vfr(dropped_frame_video):
    scan = scan_pts_ticks(dropped_frame_video)
    verdict = vfr_verdict(scan.pts)
    assert len(scan.pts) == 299 and verdict.n_deviating == 1 and verdict.vfr is False


def test_probe_reports_the_container_and_the_audio_details(cfr_video, vfr_video):
    m = probe_video(cfr_video)
    assert "mp4" in m.format_name
    assert m.audio is not None and m.audio.codec == "aac"
    assert m.audio.sample_rate > 0 and m.audio.channels >= 1
    assert abs(m.audio.start_time_s - m.start_time_s) < 0.1
    silent = probe_video(vfr_video)
    assert silent.audio is None and silent.has_audio is False


def test_probe_without_a_video_stream_raises_its_own_error(audio_only_video):
    assert issubclass(NoVideoStreamError, ProbeError)
    with pytest.raises(NoVideoStreamError):
        probe_video(audio_only_video)


def test_iter_frames_matches_pts_and_window(vfr_video):
    t_all, _ = scan_pts(vfr_video)
    frames = list(iter_frames(vfr_video))
    assert np.allclose([f.t_sec for f in frames], t_all)  # decoded timestamps == demuxed PTS

    window = list(iter_frames(vfr_video, t0=0.5, t1=1.5))
    ts = np.array([f.t_sec for f in window])
    assert ts.min() >= 0.5 - 1e-9 and ts.max() <= 1.5 + 1e-9
    expected = t_all[(t_all >= 0.5 - 1e-9) & (t_all <= 1.5 + 1e-9)]
    assert np.allclose(ts, expected)
    assert window[0].image.shape == (240, 320, 3)


def test_rotation_metadata_and_orientation(rotated_video, ffmpeg_first_frame):
    m = probe_video(rotated_video)
    assert m.rotation == 90
    ours = next(iter_frames(rotated_video, rotation_deg=m.rotation)).image
    ref = ffmpeg_first_frame(rotated_video)  # ffmpeg applies display rotation itself
    assert ours.shape == ref.shape == (320, 240, 3)
    diff_ok = np.abs(ours.astype(int) - ref.astype(int)).mean()
    wrong = np.rot90(ours, 2)  # 180° off must be clearly different
    diff_wrong = np.abs(wrong.astype(int) - ref.astype(int)).mean()
    assert diff_ok < 3.0
    assert diff_wrong > 5 * max(diff_ok, 1.0)
