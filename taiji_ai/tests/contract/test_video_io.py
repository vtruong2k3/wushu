from __future__ import annotations

import numpy as np
import pytest

from taiji_ai.io.frames import is_vfr, iter_frames, scan_pts
from taiji_ai.io.probe import probe_video


def test_probe_cfr(cfr_video):
    m = probe_video(cfr_video)
    assert (m.width, m.height) == (320, 240)
    assert m.codec == "h264"
    assert m.has_audio
    assert m.rotation == 0
    assert m.avg_frame_rate == pytest.approx(30, abs=0.01)


def test_scan_pts_cfr_is_regular(cfr_video):
    t, _ = scan_pts(cfr_video)
    assert len(t) == 60
    assert t[0] == pytest.approx(0.0, abs=1e-6)
    assert np.all(np.diff(t) > 0)
    assert not is_vfr(t)
    assert np.median(np.diff(t)) == pytest.approx(1 / 30, rel=1e-3)


def test_scan_pts_detects_vfr(vfr_video):
    t, _ = scan_pts(vfr_video)
    assert len(t) == 30 + 10  # 30 frames in the 1st second, every 3rd frame in the 2nd
    assert is_vfr(t)
    dt = np.diff(t)
    assert dt[:29] == pytest.approx(1 / 30, rel=1e-2)
    assert dt[-5:] == pytest.approx(3 / 30, rel=1e-2)


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
