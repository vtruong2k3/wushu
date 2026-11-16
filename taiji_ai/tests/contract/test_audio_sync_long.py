"""T-SYNC-06, T-SYNC-07, T-SYNC-01c: sync of long takes against a known truth (P2.04 rework, section 9.3).

Every take is built by ``helpers.sync_media.make_take_pair`` (two cameras, claps with a known global time, a known
true offset and drift); the module docstring of that helper defines the truth model used here:

* ``tp.truth_offset(t_a)`` is the true ``t_b - t_a`` on the two video timelines at the A video time ``t_a``;
* ``tp.a_video_time_of(g)`` is the A video time of the global moment ``g``.

The new names (``t_match_s`` based ``t_ref_s``, ``max_drift``) are only used inside the test bodies, so this file also
imports and collects on the first version of ``io/audio_sync.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers.sync_media import FFMPEG, TakePair, make_take_pair
from taiji_ai.config import Settings
from taiji_ai.io import audio_sync
from taiji_ai.schemas._base import read_manifest
from taiji_ai.schemas.recording import RecordingManifest

pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not available")

# The drift limit of the contract (SyncAudioParams.max_drift): beyond it a lag is implausible and can never be "ok".
MAX_DRIFT = 500e-6
# Exact true drift is 0 in T-SYNC-06; the measurement error of a clean take is far below this.
DRIFT_TOLERANCE_ZERO = 20e-6
# Half the width of the claps of a pair is about 0.5 s (pair gap 1 s): the matched position lies inside the pair.
T_REF_TOLERANCE_S = 0.6


def _pair_centre_a_video(tp: TakePair, first_clap: int) -> float:
    """The A video time of the centre of the clap pair that starts at ``clap_times_global[first_clap]``."""
    c0, c1 = tp.clap_times_global[first_clap : first_clap + 2]
    return tp.a_video_time_of((c0 + c1) / 2)


# --- T-SYNC-06: the end window does not depend on which phone stopped first (BUG-0058) -----------------------------


@pytest.mark.parametrize(
    ("end_a", "end_b", "start_b"),
    [
        pytest.param(60, 57, 0.5, id="60s_b_stops_3s_before"),
        pytest.param(60, 63, 0.5, id="60s_b_stops_3s_after"),
        pytest.param(120, 100, 0.5, id="120s_b_stops_20s_before"),
        pytest.param(120, 117, 0.5, id="120s_b_stops_3s_before"),
        pytest.param(120, 119.6, 0.5, id="120s_b_stops_0.4s_before"),
        pytest.param(120, 120, 0.5, id="120s_same_stop"),
        pytest.param(120, 123, 0.5, id="120s_b_stops_3s_after"),
        pytest.param(120, 140, 0.5, id="120s_b_stops_20s_after"),
        pytest.param(120, 119, -0.5, id="120s_b_starts_early_stops_1s_before"),
        pytest.param(300, 299.6, 0.5, id="300s_b_stops_0.4s_before"),
        pytest.param(300, 297, 0.5, id="300s_b_stops_3s_before"),
        pytest.param(300, 280, 0.5, id="300s_b_stops_20s_before"),
        pytest.param(300, 299, -0.5, id="300s_b_starts_early_stops_1s_before"),
        # A large start difference: the end window must follow the offset measured at the start, not sit at the same
        # place in B. The end margin is a few seconds, so a start difference of 0.5 s cannot show the difference.
        pytest.param(120, 120, 8.0, id="120s_b_starts_8s_late"),
        pytest.param(120, 120, -8.0, id="120s_b_starts_8s_early"),
        pytest.param(120, 121, 3.0, id="120s_b_starts_3s_late_stops_1s_after"),
        pytest.param(300, 300, 8.0, id="300s_b_starts_8s_late"),
    ],
)
def test_t_sync_06_end_window_independent_of_stop_order(
    tmp_path: Path, ingest_settings: Settings, end_a: float, end_b: float, start_b: float
):
    """Catches an end window that only works when B stops after A: a lost end or the other clap of the pair."""
    tp = make_take_pair(tmp_path / "take", ingest_settings, end_a=end_a, end_b=end_b, start_b=start_b)
    r = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    # Invariant first, so that the worst symptom (a wrong lag accepted as ok) is reported as such.
    if r.drift is not None:
        assert abs(r.drift) <= MAX_DRIFT, (
            f"a wrong end lag was accepted: drift {r.drift * 1e6:.0f} ppm, status {r.status}"
        )
    assert r.status == "ok", f"status {r.status} (reason {r.not_found_reason}), end found: {r.end.found}"
    assert r.start.found and r.end.found
    assert r.offset_s is not None and r.t_ref_s is not None and r.drift is not None
    assert abs(r.offset_s - tp.truth_offset(r.t_ref_s)) <= 0.001
    assert abs(r.drift) <= DRIFT_TOLERANCE_ZERO


# --- T-SYNC-07: drift and the reference time at the claps, windows on A's video timeline (BUG-0059) ----------------

DRIFT_CASES = [
    pytest.param(100e-6, 120, 121, id="plus100ppm_120s"),
    pytest.param(-100e-6, 120, 121, id="minus100ppm_120s"),
    pytest.param(100e-6, 300, 301, id="plus100ppm_300s"),
    pytest.param(-100e-6, 300, 301, id="minus100ppm_300s"),
    # 60 s is where taking the drift between the window centres is worst (+55 %); and B stopping before A
    pytest.param(100e-6, 60, 61, id="plus100ppm_60s"),
    pytest.param(100e-6, 120, 117, id="plus100ppm_120s_b_stops_3s_before"),
    pytest.param(-100e-6, 120, 117, id="minus100ppm_120s_b_stops_3s_before"),
]


@pytest.mark.parametrize(("drift", "end_a", "end_b"), DRIFT_CASES)
def test_t_sync_07a_drift_and_reference_time_at_the_claps(
    tmp_path: Path, ingest_settings: Settings, drift: float, end_a: float, end_b: float
):
    """Catches the offset and drift being taken at the 30 s window centres instead of at the start and end claps."""
    tp = make_take_pair(tmp_path / "take", ingest_settings, end_a=end_a, end_b=end_b, drift=drift)
    r = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    assert r.status == "ok", f"status {r.status} (reason {r.not_found_reason})"
    assert r.offset_s is not None and r.t_ref_s is not None and r.drift is not None
    assert abs(r.drift - drift) / abs(drift) <= 0.10, f"drift {r.drift * 1e6:.2f} ppm, true {drift * 1e6:.0f} ppm"
    assert abs(r.offset_s - tp.truth_offset(r.t_ref_s)) <= 0.0002
    # The reference time is where the claps are (the start pair), not the centre of the window (15 s).
    centre = _pair_centre_a_video(tp, 0)
    assert abs(r.t_ref_s - centre) <= T_REF_TOLERANCE_S, f"t_ref_s {r.t_ref_s:.2f} s, start pair centre {centre:.2f} s"


@pytest.mark.parametrize(("drift", "end_a", "end_b"), DRIFT_CASES)
def test_t_sync_07b_mapping_predicts_the_truth_at_the_end_claps(
    tmp_path: Path, ingest_settings: Settings, drift: float, end_a: float, end_b: float
):
    """Catches a pair (offset_s, drift, t_ref_s) that is inconsistent: the mapping misses the end claps by > 0.5 ms."""
    tp = make_take_pair(tmp_path / "take", ingest_settings, end_a=end_a, end_b=end_b, drift=drift)
    r = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    assert r.status == "ok", f"status {r.status} (reason {r.not_found_reason})"
    assert r.offset_s is not None and r.t_ref_s is not None and r.drift is not None
    t_a = tp.a_video_time_of(tp.clap_times_global[2])  # first clap of the end pair
    true_t_b = t_a + tp.truth_offset(t_a)
    predicted_t_b = t_a + r.offset_s + r.drift * (t_a - r.t_ref_s)
    assert abs(predicted_t_b - true_t_b) <= 0.0005, (
        f"off by {(predicted_t_b - true_t_b) * 1e3:.3f} ms at A time {t_a:.2f} s"
    )


def test_t_sync_07c_windows_on_a_video_timeline_with_audio_offset(tmp_path: Path, ingest_settings: Settings):
    """Catches windows and t_ref_s left on A's audio timeline when A's audio starts 0.4 s after its video."""
    tp = make_take_pair(
        tmp_path / "take",
        ingest_settings,
        end_a=120,
        end_b=121,
        audio_itsoffset_a=0.4,
        audio_itsoffset_b=0.3,
    )
    # precondition: the container really carries the offsets (they are not faked)
    for rec_dir, expected in ((tp.dir_a, 0.4), (tp.dir_b, 0.3)):
        man = read_manifest(rec_dir / "recording.json", RecordingManifest)
        assert man.audio is not None and abs(man.audio.start_offset_s - expected) <= 1e-3

    r = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    assert r.status == "ok", f"status {r.status} (reason {r.not_found_reason})"
    assert r.start.window_a_s == pytest.approx((0.4, 30.4), abs=1e-3)
    assert r.end.window_a_s == pytest.approx((90.4, 120.4), abs=1e-3)
    assert r.offset_s is not None and r.t_ref_s is not None and r.drift is not None
    assert abs(r.offset_s - tp.truth_offset(r.t_ref_s)) <= 0.001
    centre = _pair_centre_a_video(tp, 0)  # includes the +0.4 s of A
    assert abs(r.t_ref_s - centre) <= T_REF_TOLERANCE_S, f"t_ref_s {r.t_ref_s:.2f} s, start pair centre {centre:.2f} s"
    assert abs(r.drift) <= DRIFT_TOLERANCE_ZERO


def test_t_sync_07d_t_ref_follows_the_audio_start_of_a(tmp_path: Path, ingest_settings: Settings):
    """Catches t_ref_s left on A's audio timeline: the same sound with A's audio 0.4 s later must move t_ref_s by 0.4 s.

    The 0.6 s tolerance of 07c cannot see a missing 0.4 s; here both takes carry the same sound on A, so only the
    container offset of A differs and the two reference times (on A's timeline) must differ by exactly that offset.
    B's container offset differs too (0.3 s), which only keeps B's file from being a byte-identical duplicate that
    ingest refuses; it must not move t_ref_s.
    """
    base = make_take_pair(tmp_path / "base", ingest_settings, end_a=120, end_b=121, take_id="S01-P03-T01")
    shifted = make_take_pair(
        tmp_path / "shifted",
        ingest_settings,
        end_a=120,
        end_b=121,
        audio_itsoffset_a=0.4,
        audio_itsoffset_b=0.3,
        take_id="S01-P03-T02",
    )
    r_base = audio_sync.estimate_sync(base.dir_a, base.dir_b)
    r_shifted = audio_sync.estimate_sync(shifted.dir_a, shifted.dir_b)

    assert r_base.status == "ok", f"status {r_base.status} (reason {r_base.not_found_reason})"
    assert r_shifted.status == "ok", f"status {r_shifted.status} (reason {r_shifted.not_found_reason})"
    assert r_base.t_ref_s is not None and r_shifted.t_ref_s is not None
    assert r_shifted.t_ref_s - r_base.t_ref_s == pytest.approx(0.4, abs=0.01)


# --- T-SYNC-01c: a real container whose audio starts later than its video --------------------------------------------


def test_t_sync_01c_real_container_audio_start_offset(tmp_path: Path, ingest_settings: Settings):
    """Catches a wrong audio-to-video mapping on a real AAC/MP4 whose audio starts after its video (not faked)."""
    tp = make_take_pair(
        tmp_path / "take",
        ingest_settings,
        end_a=20,
        end_b=21,
        start_b=0.5,
        audio_itsoffset_b=0.5,
        container=".mp4",
    )
    man_b = read_manifest(tp.dir_b / "recording.json", RecordingManifest)
    assert man_b.audio is not None
    # Precondition: the container really carries the offset (AAC priming makes it about 0.44 s), it is not faked.
    assert man_b.audio.start_offset_s > 0.3

    r = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    assert r.status == "ok", f"status {r.status} (reason {r.not_found_reason})"
    assert r.offset_s is not None and r.t_ref_s is not None
    # 1 ms as the plan says (the measured error on a correct implementation is about 0.01 ms)
    assert abs(r.offset_s - tp.truth_offset(r.t_ref_s)) <= 0.001


# --- more cases, from the independent review of the first draft of these tests ----------------------------------------


@pytest.mark.parametrize(
    ("end_b", "drift"),
    [
        pytest.param(92.0, 0.0, id="b_stops_28s_early"),
        pytest.param(70.0, 0.0, id="b_stops_50s_early"),
        # B stops about 23 s early: the end claps lie at the edge of A's last 30 s, the case in which a window anchored
        # on A's own end splits the pair and matches one clap of it (a 0.3 to 0.5 s error accepted as ok, found by the
        # adversarial pass); the window of section 9.3 follows the stretch both cameras recorded
        pytest.param(97.0, 400e-6, id="b_stops_23s_early_plus400ppm"),
        pytest.param(96.6, 400e-6, id="b_stops_23.4s_early_plus400ppm"),
        pytest.param(97.4, -400e-6, id="b_stops_22.6s_early_minus400ppm"),
        pytest.param(96.8, -400e-6, id="b_stops_23.2s_early_minus400ppm"),
    ],
)
def test_t_sync_06b_the_end_window_follows_the_stretch_both_cameras_recorded(
    tmp_path: Path, ingest_settings: Settings, end_b: float, drift: float
):
    """Catches an end window anchored on A's own end: B stopping early leaves the end claps at or before its edge."""
    tp = make_take_pair(tmp_path / "take", ingest_settings, end_a=120, end_b=end_b, start_b=0.5, drift=drift)
    r = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    assert r.status == "ok", f"status {r.status}, drift {r.drift}"
    assert r.offset_s is not None and r.t_ref_s is not None and r.drift is not None
    assert abs(r.offset_s - tp.truth_offset(r.t_ref_s)) <= 0.001
    assert abs(r.drift - drift) <= max(20e-6, 0.1 * abs(drift))
    t_a = tp.a_video_time_of(tp.clap_times_global[2])  # the first end clap: the mapping must hit it
    assert abs(t_a + r.offset_s + r.drift * (t_a - r.t_ref_s) - (t_a + tp.truth_offset(t_a))) <= 0.001


@pytest.mark.parametrize(
    ("start_b", "drift", "found"),
    [
        pytest.param(-14.6, 0.0, True, id="b_14.6s_early_inside"),
        pytest.param(14.6, 0.0, True, id="b_14.6s_late_inside"),
        pytest.param(-15.3, 0.0, False, id="b_15.3s_early_beyond"),
        pytest.param(15.3, 0.0, False, id="b_15.3s_late_beyond"),
        # just beyond the range: with no guard zone one clap of the pair matched inside it (300 ms off) and was ok
        pytest.param(-15.05, 300e-6, False, id="b_15.05s_early_plus300ppm_beyond"),
    ],
)
def test_t_sync_06e_a_start_difference_beyond_max_lag_is_refused_not_misread(
    tmp_path: Path, ingest_settings: Settings, start_b: float, drift: float, found: bool
):
    """Catches a start search whose range ends at max_lag_s: a true match just beyond it is invisible and one clap of
    the pair matches inside it. The start window is searched a guard zone wider and a lag beyond max_lag_s refused."""
    tp = make_take_pair(tmp_path / "take", ingest_settings, end_a=120, end_b=121, start_b=start_b, drift=drift)
    r = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    if found:
        assert r.status == "ok", f"status {r.status}"
        assert r.offset_s is not None and r.t_ref_s is not None
        assert abs(r.offset_s - tp.truth_offset(r.t_ref_s)) <= 0.001
    else:
        assert r.status == "not_found" and r.not_found_reason == "clap_not_found", f"status {r.status}, {r.offset_s}"
        assert r.offset_s is None and r.drift is None and r.t_ref_s is None
        assert r.start.found is False and r.start.lag_s is None


def test_t_sync_07g_t_ref_stays_at_the_claps_in_noise(tmp_path: Path, ingest_settings: Settings):
    """Catches a reference time that noise drags to the middle of the window (the centroid of the whole product).

    Noise (sigma 0.02) and a weak clap on B (0.5): the product of the two noise envelopes carries no information but
    plenty of mass; ``t_ref_s`` must still be at the claps (the old centroid sat 2 to 3 s away, in the window), or
    the mapping drifts off the claps.
    """
    tp = make_take_pair(
        tmp_path / "take",
        ingest_settings,
        end_a=120,
        end_b=121,
        drift=400e-6,
        noise_a=0.02,
        noise_b=0.02,
        clap_amplitude_b=0.5,
    )
    r = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    assert r.status == "ok", f"status {r.status} (reason {r.not_found_reason})"
    assert r.offset_s is not None and r.t_ref_s is not None and r.drift is not None
    assert abs(r.t_ref_s - _pair_centre_a_video(tp, 0)) <= T_REF_TOLERANCE_S, f"t_ref_s {r.t_ref_s:.2f} s"
    for first_clap in (0, 2):  # both pairs: the mapping must hit them
        for clap in tp.clap_times_global[first_clap : first_clap + 2]:
            t_a = tp.a_video_time_of(clap)
            predicted = t_a + r.offset_s + r.drift * (t_a - r.t_ref_s)
            assert abs(predicted - (t_a + tp.truth_offset(t_a))) <= 0.001, f"clap at {t_a:.1f} s"


def test_t_sync_06d_b_start_window_has_room_for_a_shift_beyond_a_window(tmp_path: Path, ingest_settings: Settings):
    """Catches: B's start slice no longer than A's window: claps near the end of A's window, shown later by B, are cut.

    A's start window is [0, 30]; the start pair is at 26 s and B started 10 s earlier, so B hears it at 36 s: B's slice
    must be ``window + max_lag`` (45 s) long, not 30 s.
    """
    tp = make_take_pair(tmp_path / "take", ingest_settings, end_a=120, end_b=121, start_b=-10.0, start_pair_s=26.0)
    r = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    assert r.status == "ok", f"status {r.status} (reason {r.not_found_reason})"
    assert r.offset_s is not None and r.t_ref_s is not None and r.drift is not None
    assert abs(r.offset_s - tp.truth_offset(r.t_ref_s)) <= 0.001
    assert abs(r.drift) <= DRIFT_TOLERANCE_ZERO


def test_t_sync_06c_the_order_of_the_two_folders_does_not_matter(tmp_path: Path, ingest_settings: Settings):
    """Catches the camera swap (A is the camera that sorts first) failing on a long take where B stops before A."""
    tp = make_take_pair(tmp_path / "take", ingest_settings, end_a=120, end_b=117, start_b=0.5)
    forward = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)
    backward = audio_sync.estimate_sync(tp.dir_b, tp.dir_a)

    assert forward.status == "ok"
    assert (forward.cam_a, forward.cam_b) == ("camA", "camB") == (backward.cam_a, backward.cam_b)
    assert (backward.status, backward.offset_s, backward.drift, backward.t_ref_s) == (
        forward.status,
        forward.offset_s,
        forward.drift,
        forward.t_ref_s,
    )
    assert (backward.start, backward.end) == (forward.start, forward.end)


@pytest.mark.parametrize(("drift", "end_a", "end_b"), DRIFT_CASES[:4])
def test_t_sync_07e_window_lags_are_the_truth_at_their_own_claps(
    tmp_path: Path, ingest_settings: Settings, drift: float, end_a: float, end_b: float
):
    """Catches start.lag_s and end.lag_s (written to sync.json) that are right only through offset_s and drift."""
    tp = make_take_pair(tmp_path / "take", ingest_settings, end_a=end_a, end_b=end_b, drift=drift)
    r = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    assert r.status == "ok", f"status {r.status} (reason {r.not_found_reason})"
    assert r.start.lag_s is not None and r.end.lag_s is not None
    start_centre = _pair_centre_a_video(tp, 0)
    end_centre = _pair_centre_a_video(tp, 2)
    assert abs(r.start.lag_s - tp.truth_offset(start_centre)) <= 0.0005
    assert abs(r.end.lag_s - tp.truth_offset(end_centre)) <= 0.0005
    assert r.start.lag_s == r.offset_s  # the offset of the take is the start lag


def test_t_sync_07f_real_aac_container_long_take_with_drift_and_offsets(tmp_path: Path, ingest_settings: Settings):
    """Catches errors that appear only with a real container: AAC priming, an audio offset on A and on B, a drift."""
    true_drift = 100e-6
    tp = make_take_pair(
        tmp_path / "take",
        ingest_settings,
        end_a=120,
        end_b=121,
        drift=true_drift,
        audio_itsoffset_a=0.5,
        audio_itsoffset_b=0.3,
        container=".mp4",
    )
    r = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    assert r.status == "ok", f"status {r.status} (reason {r.not_found_reason})"
    assert r.offset_s is not None and r.t_ref_s is not None and r.drift is not None
    assert abs(r.offset_s - tp.truth_offset(r.t_ref_s)) <= 0.0015  # AAC is lossy: a little looser than the PCM takes
    assert abs(r.drift - true_drift) / true_drift <= 0.15
    centre = _pair_centre_a_video(tp, 0)  # on A's video timeline: includes A's audio offset
    assert abs(r.t_ref_s - centre) <= T_REF_TOLERANCE_S


@pytest.mark.parametrize(
    ("drift", "end_pair_s", "edge"),
    [
        # A's end window is the last 30 s of the take (here 90..120 s). B's slice must be wider than that window by the
        # margin: the drift moves a clap of B by up to 50 ms, past the edge of a slice cut exactly to the window.
        # A clean pair gives a peak ratio of 2.0 (its own second lobe at one pair gap); a cut clap lowers it.
        pytest.param(400e-6, 118.97, "end", id="plus400ppm_pair_at_the_window_end"),
        pytest.param(-400e-6, 89.97, "start", id="minus400ppm_pair_at_the_window_start"),
    ],
)
def test_t_sync_06f_a_clap_at_the_window_edge_pushed_by_drift_is_not_cut_off(
    tmp_path: Path, ingest_settings: Settings, drift: float, end_pair_s: float, edge: str
):
    """Catches a B slice cut to A's window: the clap pushed over its edge by the drift is lost and the match is weak."""
    tp = make_take_pair(tmp_path / "take", ingest_settings, end_a=120, end_b=120, drift=drift, end_pair_s=end_pair_s)
    r = audio_sync.estimate_sync(tp.dir_a, tp.dir_b)

    assert r.status == "ok", f"status {r.status} (reason {r.not_found_reason}) with a clap at the {edge} of the window"
    assert r.offset_s is not None and r.t_ref_s is not None and r.drift is not None
    assert abs(r.offset_s - tp.truth_offset(r.t_ref_s)) <= 0.0005
    assert abs(r.drift - drift) / abs(drift) <= 0.10, f"drift {r.drift * 1e6:.1f} ppm, true {drift * 1e6:.0f} ppm"
    assert r.end.peak_ratio is not None and r.end.peak_ratio >= 1.9, f"end peak ratio {r.end.peak_ratio}"
