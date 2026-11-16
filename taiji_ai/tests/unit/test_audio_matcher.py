"""T-SYNC-09: the envelope matcher ``xcorr_lag`` and the sync parameters (P2.04 rework, section 9.3 of the task file).

Pure numpy, no ffmpeg. The envelopes are crafted so that each property is isolated:

* the lag is *B minus A* in seconds (positive when B shows the same event later);
* ``t_match_s`` is a time on A's envelope (seconds from the start of ``env_a``);
* the sub-sample test samples smooth Gaussian bursts analytically at a fractional delay: the true lag is exact;
* the gate tests use pairs whose peak, peak ratio or crest sits on one side of a threshold while the other two
  quantities are far from theirs, so one gate alone decides (the pair is calibrated with all gates open and the
  calibration is asserted, so a changed random stream fails loudly instead of silently testing something else);
* the matcher does not care about the rate: gate pairs use 1 kHz to stay small, precision and timing tests use 16 kHz.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from taiji_ai.io import audio_sync

SR_ENV = 16000  # the real envelopes are at the audio rate
SR_LOW = 1000  # crafted gate pairs
OPEN_GATES = {"min_peak": 0.0, "min_peak_ratio": 0.0, "min_crest": 0.0}
# The section 9.3 defaults of the three gates and of the search range (``ratio_floor`` is checked on its own).
SPEC_GATES = {"max_lag_s": 15.0, "min_peak": 0.25, "min_peak_ratio": 1.25, "min_crest": 2.5}


# --------------------------------------------------------------------------------------------------------------------
# crafted envelopes
# --------------------------------------------------------------------------------------------------------------------


def _gauss(n: int, centre_s: float, sr: int, sigma_s: float, height: float = 1.0, delay_samples: float = 0.0):
    """A Gaussian burst sampled analytically (no interpolation), centre at ``centre_s + delay_samples / sr``."""
    t = np.arange(n) / sr
    return height * np.exp(-0.5 * ((t - centre_s - delay_samples / sr) / sigma_s) ** 2)


def _burst_pattern(n: int, sr: int, seed: int, bursts: int = 10, sigma_s: float = 0.010) -> np.ndarray:
    """An irregular train of Gaussian bursts: sharp, unique autocorrelation, zero baseline."""
    rng = np.random.default_rng(seed)
    centres = rng.uniform(0.15, n / sr - 0.15, bursts)
    heights = rng.uniform(0.8, 1.2, bursts)
    return sum(_gauss(n, c, sr, sigma_s, h) for c, h in zip(centres, heights, strict=True))


def _noisy_pair(noise: float, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """A (6 s) and B (16 s) share one burst pattern, B shifted by +3.0 s; both get independent non-negative noise.

    The pattern is unique in B, so the peak ratio stays high while ``noise`` lowers the normalised peak:
    about 0.21 at noise 0.85, 0.28 at 0.7 and 0.125 at 1.2 (asserted by the tests that use them).
    """
    rng = np.random.default_rng(seed)
    n_a, n_b, shift = 6 * SR_LOW, 16 * SR_LOW, 3 * SR_LOW
    pattern = _burst_pattern(n_a, SR_LOW, seed + 100)
    a = pattern + noise * rng.random(n_a)
    b = np.zeros(n_b)
    b[shift : shift + n_a] = pattern
    return a, b + noise * rng.random(n_b)


def _two_copies(amp_first: float, amp_second: float) -> tuple[np.ndarray, np.ndarray]:
    """A (1.5 s) holds a burst pattern; B (5 s) holds it twice, at +0.5 s and +2.5 s, with these amplitudes.

    No noise: the two lags peak at the amplitudes' ratio, so the peak ratio is about ``amp_first / amp_second``.
    """
    n_a = 1500
    pattern = _burst_pattern(n_a, SR_LOW, seed=3)
    b = np.zeros(5000)
    b[500 : 500 + n_a] += amp_first * pattern
    b[2500 : 2500 + n_a] += amp_second * pattern
    return pattern, b


def _spike_array(height: float) -> np.ndarray:
    """4 s of baseline 1.0 (+5 % noise) with one spike: the crest factor (max / mean) grows with ``height``."""
    env = 1.0 + 0.05 * np.random.default_rng(5).random(4000)
    env[1700] += height
    return env


def _crest(env: np.ndarray) -> float:
    return float(env.max() / env.mean())


def _probe(a: np.ndarray, b: np.ndarray, sr: int, max_lag_s: float):
    """The matcher with every gate open: reports the measured peak and ratio of a crafted pair."""
    return audio_sync.xcorr_lag(a, b, sr, max_lag_s=max_lag_s, **OPEN_GATES)


# --------------------------------------------------------------------------------------------------------------------
# precision and sign
# --------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("delay_samples", [0.0, 0.25, 0.5, 0.75, 3.4, -0.25, -0.5, -0.75, -3.4])
def test_t_sync_09_sub_sample_precision_under_0_01_ms(delay_samples):
    """Catches: no sub-sample interpolation (error up to 31 us) or an interpolation with the wrong sign."""
    sigma_s = 0.006  # an envelope-like width, 96 samples
    a = _gauss(2 * SR_ENV, 1.0, SR_ENV, sigma_s)
    b = _gauss(2 * SR_ENV, 1.0, SR_ENV, sigma_s, delay_samples=delay_samples)
    est = audio_sync.xcorr_lag(a, b, SR_ENV, max_lag_s=2.0)  # wide enough to hold a second peak beyond +-0.5 s
    assert est.found
    assert abs(est.lag_s - delay_samples / SR_ENV) < 1e-5, (est.lag_s * SR_ENV, delay_samples)


def test_t_sync_09_lag_is_b_minus_a_and_swapping_negates_it():
    """Catches: the sign of the lag reversed (B later must give a positive lag)."""
    a = _gauss(3 * SR_LOW, 1.0, SR_LOW, 0.01)
    b = _gauss(3 * SR_LOW, 1.3, SR_LOW, 0.01)
    forward = audio_sync.xcorr_lag(a, b, SR_LOW, max_lag_s=1.0)
    backward = audio_sync.xcorr_lag(b, a, SR_LOW, max_lag_s=1.0)
    assert forward.found and backward.found
    assert abs(forward.lag_s - 0.3) < 1e-3
    assert abs(backward.lag_s + 0.3) < 1e-3


# --------------------------------------------------------------------------------------------------------------------
# the three gates, each alone
# --------------------------------------------------------------------------------------------------------------------


def test_t_sync_09_min_peak_gate_alone():
    """Catches: ``min_peak`` removed or ``found`` forced true (a correlated but weak match accepted)."""
    a, b = _noisy_pair(noise=1.2)
    probe = _probe(a, b, SR_LOW, max_lag_s=8.0)
    # calibration: weak (0.05..0.2), unique (ratio well above 1.25) and peaky (crest well above 2.5)
    assert 0.05 < probe.peak < 0.2, probe
    assert probe.peak_ratio >= 1.5, probe
    assert min(_crest(a), _crest(b)) >= 3.0

    default = audio_sync.xcorr_lag(a, b, SR_LOW, max_lag_s=8.0)
    assert default.found is False
    assert default.lag_s is None
    # the diagnostics of a rejected window are kept (the sync result reports them)
    assert default.peak == pytest.approx(probe.peak)
    assert default.peak_ratio == pytest.approx(probe.peak_ratio)

    relaxed = audio_sync.xcorr_lag(a, b, SR_LOW, max_lag_s=8.0, min_peak=0.05)
    assert relaxed.found is True
    assert abs(relaxed.lag_s - 3.0) < 5e-3  # the weak match is still the right one


def test_t_sync_09_min_peak_ratio_gate_alone():
    """Catches: ``min_peak_ratio`` removed or ``found`` forced true (an ambiguous, twice-present match accepted)."""
    # equal pair would give a ratio of 1.0 +- rounding; 3 % apart keeps ``>= 1.0`` deterministic and far below 1.25
    pattern, b = _two_copies(1.0, 0.97)
    probe = _probe(pattern, b, SR_LOW, max_lag_s=4.0)
    assert probe.peak > 0.5, probe  # strong: only the ratio can reject it
    assert 1.0 <= probe.peak_ratio < 1.1, probe

    default = audio_sync.xcorr_lag(pattern, b, SR_LOW, max_lag_s=4.0)
    assert default.found is False
    assert default.lag_s is None

    relaxed = audio_sync.xcorr_lag(pattern, b, SR_LOW, max_lag_s=4.0, min_peak_ratio=1.0)
    assert relaxed.found is True
    assert abs(relaxed.lag_s - 0.5) < 2e-3  # one of the two lags: the stronger copy

    # the best lag follows the stronger copy, not the first or the closest to zero
    pattern, swapped = _two_copies(0.97, 1.0)
    relaxed = audio_sync.xcorr_lag(pattern, swapped, SR_LOW, max_lag_s=4.0, min_peak_ratio=1.0)
    assert relaxed.found is True
    assert abs(relaxed.lag_s - 2.5) < 2e-3


def test_t_sync_09_min_crest_gate_alone():
    """Catches: ``min_crest`` removed or ``found`` forced true (a flat envelope accepted as a clap)."""
    env = 1.0 + np.random.default_rng(11).random(4000)  # uniform 1..2: crest about 1.34
    twin = env.copy()
    assert _crest(env) < 1.5
    probe = _probe(env, twin, SR_LOW, max_lag_s=15.0)
    assert probe.peak > 0.99 and probe.peak_ratio >= 5.0, probe  # identical and unique: only the crest can reject it

    default = audio_sync.xcorr_lag(env, twin, SR_LOW)
    assert default.found is False
    assert default.lag_s is None

    relaxed = audio_sync.xcorr_lag(env, twin, SR_LOW, min_crest=0.0)
    assert relaxed.found is True
    assert abs(relaxed.lag_s) < 1e-3


# --------------------------------------------------------------------------------------------------------------------
# the defaults
# --------------------------------------------------------------------------------------------------------------------


def test_t_sync_09_sync_audio_params_defaults():
    """Catches: a changed default of the recorded parameters (they are written into sync.json)."""
    expected = {
        "sr": 16000,
        "hp_hz": 300.0,
        "lp_hz": 50.0,
        "window_s": 30.0,
        "max_lag_s": 15.0,
        "min_peak": 0.25,
        "min_peak_ratio": 1.25,
        "min_crest": 2.5,
        "max_drift": 500e-6,  # phone clocks differ by tens of ppm; also the cross-check of the two windows
        "start_guard_s": 3.5,  # the start window is searched this much beyond max_lag_s and the excess refused
        "end_margin_s": 3.5,  # wider than the gap of a clap pair: see section 9.3 (the 9091 ppm case of T-SYNC-08)
        "ratio_floor": 0.01,
    }
    params = audio_sync.SyncAudioParams()
    missing = object()
    wrong = {k: (getattr(params, k, missing), v) for k, v in expected.items() if getattr(params, k, missing) != v}
    assert not wrong, wrong


def test_t_sync_09_matcher_defaults_come_from_the_params():
    """Catches: the matcher and the parameter dataclass carrying two copies of a default (single source)."""
    signature = inspect.signature(audio_sync.xcorr_lag).parameters
    params = audio_sync.SyncAudioParams()
    for name in ("max_lag_s", "min_peak", "min_peak_ratio", "min_crest", "ratio_floor"):
        assert name in signature, name
        assert signature[name].default == getattr(params, name), name


def _bracket(gate: str):
    """Two crafted pairs per default gate: ``below`` just on the rejecting side, ``above`` just on the accepting side.

    Each sits within about 0.05 (peak), 0.07 (ratio), 0.3 (crest) or 1 s (search range) of the threshold, with the
    other quantities far from theirs; the calibration is asserted so that a changed fixture cannot pass silently.
    """
    if gate == "min_peak":  # threshold 0.25
        below, above = _noisy_pair(0.85), _noisy_pair(0.7)
        lo, hi = _probe(*below, SR_LOW, 8.0), _probe(*above, SR_LOW, 8.0)
        assert 0.20 < lo.peak < 0.25 and 0.25 < hi.peak < 0.30, (lo, hi)
        assert lo.peak_ratio >= 2.0 and hi.peak_ratio >= 2.0, (lo, hi)
        assert min(_crest(x) for x in (*below, *above)) >= 3.0
    elif gate == "min_peak_ratio":  # threshold 1.25
        below, above = _two_copies(1.0, 0.85), _two_copies(1.0, 0.75)
        lo, hi = _probe(*below, SR_LOW, 4.0), _probe(*above, SR_LOW, 4.0)
        assert 1.12 < lo.peak_ratio < 1.25 and 1.25 < hi.peak_ratio < 1.40, (lo, hi)
        assert lo.peak > 0.5 and hi.peak > 0.5, (lo, hi)
    elif gate == "min_crest":  # threshold 2.5
        below, above = (_spike_array(1.3),) * 2, (_spike_array(1.7),) * 2
        assert 2.2 < _crest(below[0]) < 2.5 and 2.5 < _crest(above[0]) < 2.8, (_crest(below[0]), _crest(above[0]))
        lo, hi = _probe(*below, SR_LOW, 15.0), _probe(*above, SR_LOW, 15.0)
        assert lo.peak > 0.99 and hi.peak > 0.99 and lo.peak_ratio >= 5.0 and hi.peak_ratio >= 5.0, (lo, hi)
    else:  # max_lag_s, threshold 15 s: a clean burst 14 s and 16 s later
        a = _gauss(3 * SR_LOW, 1.0, SR_LOW, 0.01)
        below, above = (a, _gauss(22 * SR_LOW, 17.0, SR_LOW, 0.01)), (a, _gauss(22 * SR_LOW, 15.0, SR_LOW, 0.01))
        hi = _probe(*above, SR_LOW, 15.0)
        assert hi.peak > 0.9 and abs(hi.lag_s - 14.0) < 1e-2, hi
    return below, above


@pytest.mark.parametrize("gate", ["min_peak", "min_peak_ratio", "min_crest", "max_lag_s"])
def test_t_sync_09_default_gates_sit_at_the_specified_thresholds(gate):
    """Catches: a default threshold moved (a call without the gate arguments must act as the section 9.3 values)."""
    below, above = _bracket(gate)
    for (a, b), expected in ((below, False), (above, True)):
        default = audio_sync.xcorr_lag(a, b, SR_LOW)
        explicit = audio_sync.xcorr_lag(a, b, SR_LOW, **SPEC_GATES)
        assert default == explicit, (gate, expected)
        assert default.found is expected, (gate, expected, default)


# --------------------------------------------------------------------------------------------------------------------
# no made-up numbers
# --------------------------------------------------------------------------------------------------------------------


def test_t_sync_09_ratio_floor_replaces_the_sentinel_for_a_clean_pulse():
    """Catches: the 999 sentinel (or a cap) for 'no second peak'; a hard-coded floor; a ratio against the raw second."""
    a = _gauss(2000, 0.8, SR_LOW, 0.01)
    b = _gauss(6000, 2.3, SR_LOW, 0.01)  # one clean pulse, B later by 1.5 s: no second peak outside +-0.5 s
    est = audio_sync.xcorr_lag(a, b, SR_LOW, max_lag_s=3.0)
    assert est.found is True
    assert est.peak > 0.95
    assert est.peak_ratio == pytest.approx(est.peak / 0.01, rel=1e-6)  # about 100, never 999
    assert est.peak_ratio < 150.0

    est = audio_sync.xcorr_lag(a, b, SR_LOW, max_lag_s=3.0, ratio_floor=0.05)
    assert est.found is True
    assert est.peak_ratio == pytest.approx(est.peak / 0.05, rel=1e-6)  # about 20


def test_t_sync_09_ratio_is_best_over_second_when_the_second_is_above_the_floor():
    """Catches: an inverted ratio, or the floor applied when a real second peak exists."""
    pattern, b = _two_copies(1.0, 0.85)
    est = _probe(pattern, b, SR_LOW, max_lag_s=4.0)
    assert est.peak_ratio == pytest.approx(1.0 / 0.85, rel=0.03)  # the other copy peaks at 0.85 of the best
    # raising the floor above the second peak (and below the best one) turns the ratio into best / floor
    second = est.peak / est.peak_ratio
    floor = (second + est.peak) / 2.0
    raised = audio_sync.xcorr_lag(pattern, b, SR_LOW, max_lag_s=4.0, ratio_floor=floor, **OPEN_GATES)
    assert raised.peak_ratio == pytest.approx(raised.peak / floor, rel=1e-6)
    assert 1.0 <= raised.peak_ratio < est.peak_ratio


def test_t_sync_09_ratio_is_never_below_one():
    """Catches: a ratio below 1 (a floor above the best peak): the schema refuses it, and it means nothing."""
    pattern, b = _two_copies(1.0, 0.85)
    est = audio_sync.xcorr_lag(pattern, b, SR_LOW, max_lag_s=4.0, ratio_floor=0.99, **OPEN_GATES)
    assert est.peak < 0.99, est  # the premise: the floor is above the best peak of this pair
    assert est.peak_ratio == 1.0


@pytest.mark.parametrize("max_lag_s", [0.1, 15.0])
def test_t_sync_09_window_too_short_for_a_second_peak_is_not_found(max_lag_s):
    """Catches: a match accepted as unique when no lag exists outside the 0.2 s exclusion (the 999 sentinel)."""
    a = _gauss(150, 0.075, SR_LOW, 0.01)  # 0.15 s: every lag is within the 0.2 s exclusion radius
    est = audio_sync.xcorr_lag(a, a.copy(), SR_LOW, max_lag_s=max_lag_s)
    assert est.found is False
    assert est.lag_s is None
    assert est.peak_ratio is None  # not measurable: None, never a made-up number
    assert est.peak is not None and 0.95 < est.peak <= 1.0  # the peak itself was measured and is reported

    # control: the same burst in a 3 s window has room for a second peak and is found
    long_a = _gauss(3000, 1.0, SR_LOW, 0.01)
    control = audio_sync.xcorr_lag(long_a, long_a.copy(), SR_LOW, max_lag_s=1.0)
    assert control.found is True
    assert control.peak_ratio is not None and control.peak_ratio > 10.0


@pytest.mark.parametrize("sign", [1, -1])
def test_t_sync_09_offset_beyond_max_lag_is_not_found(sign):
    """Catches: ``max_lag_s`` ignored, applied to one side only, or applied with the wrong scale."""
    a = _gauss(8000, 4.0, SR_LOW, 0.01)
    far = _gauss(8000, 4.0 + sign * 2.0, SR_LOW, 0.01)
    near = _gauss(8000, 4.0 + sign * 0.9, SR_LOW, 0.01)

    refused = audio_sync.xcorr_lag(a, far, SR_LOW, max_lag_s=1.0)
    assert refused.found is False
    assert refused.lag_s is None

    wide = audio_sync.xcorr_lag(a, far, SR_LOW, max_lag_s=3.0)  # control: the offset is real and findable
    assert wide.found is True
    assert abs(wide.lag_s - sign * 2.0) < 2e-3

    inside = audio_sync.xcorr_lag(a, near, SR_LOW, max_lag_s=1.0)  # control: inside the range it is accepted
    assert inside.found is True
    assert abs(inside.lag_s - sign * 0.9) < 2e-3


# --------------------------------------------------------------------------------------------------------------------
# the matched position
# --------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("baseline", [0.0, 1.0])
@pytest.mark.parametrize(("centre_a_s", "lag_s"), [(1.3, 1.8), (4.3, -1.8), (1.3, 0.0)])
def test_t_sync_09_t_match_is_the_burst_position_on_a(centre_a_s, lag_s, baseline):
    """Catches: t_match_s = window centre, a position on B's timeline, a product at lag 0, or a product of the raw
    envelopes (a noise floor under the burst would pull the centroid to the middle of the window)."""
    sigma_s = 0.005
    height = 1.0 if baseline == 0.0 else 3.0  # on a floor of 1.0 the burst still has a crest factor of about 4
    a = baseline + _gauss(6 * SR_ENV, centre_a_s, SR_ENV, sigma_s, height)  # 6 s, centre of the window at 3.0 s
    b = baseline + _gauss(12 * SR_ENV, centre_a_s + lag_s + 2.0, SR_ENV, sigma_s, height)  # B 2 s later, plus the lag
    est = audio_sync.xcorr_lag(a, b, SR_ENV, max_lag_s=4.0)
    assert est.found is True
    assert abs(est.lag_s - (lag_s + 2.0)) < 1e-4
    assert est.t_match_s is not None
    # 20 ms: the positive part of the product of two zero-mean envelopes carries a small pedestal that pulls the
    # centroid by a few ms; the wrong implementations (the window centre, a position on B, a raw product) are
    # far beyond it
    assert abs(est.t_match_s - centre_a_s) < 0.02, est.t_match_s


@pytest.mark.parametrize(("height_1", "height_2", "expected_s"), [(1.0, 1.0, 1.5), (1.0, 0.5, 1.2)])
def test_t_sync_09_t_match_is_the_evidence_weighted_centre_of_two_bursts(height_1, height_2, expected_s):
    """Catches: the midpoint of the window or of the first and last burst instead of the centroid of the product."""
    sigma_s = 0.005
    # bursts of A at 1.0 s and 2.0 s; the product at the best lag weighs them by height squared: (1*1 + 2*w) / (1 + w)
    a = _gauss(6 * SR_ENV, 1.0, SR_ENV, sigma_s, height_1) + _gauss(6 * SR_ENV, 2.0, SR_ENV, sigma_s, height_2)
    b = _gauss(12 * SR_ENV, 3.4, SR_ENV, sigma_s, height_1) + _gauss(12 * SR_ENV, 4.4, SR_ENV, sigma_s, height_2)
    est = audio_sync.xcorr_lag(a, b, SR_ENV, max_lag_s=4.0)
    assert est.found is True
    assert abs(est.lag_s - 2.4) < 1e-4
    assert est.t_match_s is not None
    assert abs(est.t_match_s - expected_s) < 0.02, est.t_match_s
    assert 0.0 <= est.t_match_s <= a.size / SR_ENV


def test_t_sync_09_t_match_counts_only_the_positive_part_of_the_product():
    """Catches: the absolute value of the product (evidence against the match must not move the matched position)."""
    sigma_s = 0.005
    # A: bursts at 1.0 s (1.0), 1.7 s (0.6) and 5.0 s (0.5). B = floor 1.0 with the same first two bursts, 2.4 s later
    # and twice as high, and a dip (not a burst) where A's third burst lands: positive product at 1.0 and 1.7 s only,
    # a negative one at 5.0 s. Positive part: (2.0 * 1.0 + 0.72 * 1.7) / 2.72 = 1.185 s; with the absolute value 1.73 s.
    a = (
        _gauss(6 * SR_ENV, 1.0, SR_ENV, sigma_s, 1.0)
        + _gauss(6 * SR_ENV, 1.7, SR_ENV, sigma_s, 0.6)
        + _gauss(6 * SR_ENV, 5.0, SR_ENV, sigma_s, 0.5)
    )
    b = (
        1.0
        + _gauss(12 * SR_ENV, 3.4, SR_ENV, sigma_s, 2.0)
        + _gauss(12 * SR_ENV, 4.1, SR_ENV, sigma_s, 1.2)
        - _gauss(12 * SR_ENV, 7.4, SR_ENV, sigma_s, 0.9)
    )
    assert _crest(b) > 2.5  # the crest gate must not be what decides
    est = audio_sync.xcorr_lag(a, b, SR_ENV, max_lag_s=4.0)
    assert est.found is True
    assert abs(est.lag_s - 2.4) < 1e-4
    assert est.t_match_s is not None
    assert abs(est.t_match_s - 1.185) < 0.03, est.t_match_s


def _cases_not_found():
    """(label, call) pairs, every one of which must come back not found."""
    weak_a, weak_b = _noisy_pair(noise=1.2)
    pattern, twice = _two_copies(1.0, 0.97)
    short = _gauss(400, 0.2, SR_LOW, 0.01)
    burst_a, burst_far = _gauss(8000, 4.0, SR_LOW, 0.01), _gauss(8000, 6.0, SR_LOW, 0.01)
    flat = np.full(2000, 0.3)
    return [
        ("weak", lambda: audio_sync.xcorr_lag(weak_a, weak_b, SR_LOW, max_lag_s=8.0)),
        ("ambiguous", lambda: audio_sync.xcorr_lag(pattern, twice, SR_LOW, max_lag_s=4.0)),
        ("no second peak", lambda: audio_sync.xcorr_lag(short, short.copy(), SR_LOW, max_lag_s=0.1)),
        ("beyond max_lag_s", lambda: audio_sync.xcorr_lag(burst_a, burst_far, SR_LOW, max_lag_s=1.0)),
        ("empty", lambda: audio_sync.xcorr_lag(np.zeros(0), np.zeros(0), SR_LOW)),
        ("constant", lambda: audio_sync.xcorr_lag(flat, flat.copy(), SR_LOW, min_crest=0.0)),
    ]


def test_t_sync_09_not_found_has_no_lag_and_no_t_match():
    """Catches: a lag or a matched position reported for a window that was rejected."""
    for label, call in _cases_not_found():
        est = call()
        assert est.found is False, label
        assert est.lag_s is None, label
        assert est.t_match_s is None, label


# --------------------------------------------------------------------------------------------------------------------
# clipping and degenerate input
# --------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_t_sync_09_identical_arrays_peak_is_at_most_one(dtype):
    """Catches: an exact match reported as 1.0000002 (rounding), which the schema refuses; no clipping to [0, 1]."""
    for seed in range(40):  # in float32 about half of the seeds round above 1.0 without the clip
        env = (np.random.default_rng(1000 + seed).random(3000) ** 4).astype(dtype)
        est = audio_sync.xcorr_lag(env, env.copy(), SR_LOW)
        assert est.found is True, seed
        assert 0.999 <= est.peak <= 1.0, (seed, repr(est.peak))
        assert abs(est.lag_s) < 1e-3, seed


def test_t_sync_09_negative_correlation_peak_is_clipped_to_zero():
    """Catches: a negative peak reported as measured (the schema wants 0..1); the lower clip missing."""
    n = 400
    a = _gauss(n, 0.2, SR_LOW, 0.04)
    b = 1.0 - a  # non-negative and anti-correlated with A
    a_zm, b_zm = a - a.mean(), b - b.mean()
    for k in range(-3, 4):  # calibration: every correlation within +-3 samples is negative
        value = np.dot(a_zm[max(0, -k) : n - max(0, k)], b_zm[max(0, k) : n - max(0, -k)])
        assert value < 0.0, (k, value)
    est = audio_sync.xcorr_lag(a, b, SR_LOW, max_lag_s=0.003, min_crest=0.0)
    assert est.found is False
    assert est.lag_s is None
    assert est.peak == 0.0


def test_t_sync_09_empty_and_constant_arrays_are_not_found_without_an_exception():
    """Catches: an exception or an invented lag on empty input or zero-variance envelopes (NaN from 0 / 0)."""
    empty = np.zeros(0)
    spike = _gauss(2000, 1.0, SR_LOW, 0.01)
    flat = np.full(2000, 0.3)
    pairs = {
        "both empty": (empty, empty),
        "a empty": (empty, spike),
        "b empty": (spike, empty),
        "both zeros": (np.zeros(2000), np.zeros(2000)),
        "both flat": (flat, flat.copy()),
        "a flat": (flat, spike),
        "b flat": (spike, flat),
    }
    for label, (a, b) in pairs.items():
        for gates in ({}, {"min_crest": 0.0}):  # the crest gate may reject first: also test the variance guard itself
            est = audio_sync.xcorr_lag(a, b, SR_LOW, **gates)
            assert est.found is False, (label, gates)
            assert est.lag_s is None, (label, gates)


# --------------------------------------------------------------------------------------------------------------------
# more cases, from the independent review of the first version of this file
# --------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("pedestal_on", ["b", "a"])
def test_t_sync_09_crest_gate_applies_to_either_array(pedestal_on):
    """Catches: the crest gate on one array only, or combined with 'and' (a hum pedestal on one microphone)."""
    spiky = _spike_array(1.7)
    humming = spiky + 2.0  # the same shape (the correlation stays perfect) but a pedestal lowers the crest
    a, b = (spiky, humming) if pedestal_on == "b" else (humming, spiky)
    assert _crest(spiky) > 2.5 > _crest(humming), (_crest(spiky), _crest(humming))  # calibration
    assert _probe(a, b, SR_LOW, 1.0).peak > 0.99

    rejected = audio_sync.xcorr_lag(a, b, SR_LOW, max_lag_s=1.0)
    assert rejected.found is False and rejected.lag_s is None
    assert audio_sync.xcorr_lag(a, b, SR_LOW, max_lag_s=1.0, min_crest=0.0).found is True


def test_t_sync_09_second_peak_is_looked_for_inside_the_search_range_only():
    """Catches: a second peak taken from the whole correlation, so a copy beyond max_lag_s makes the match ambiguous."""
    pattern, b = _two_copies(1.0, 1.0)  # equal copies at +0.5 s and +2.5 s
    both_in_range = audio_sync.xcorr_lag(pattern, b, SR_LOW, max_lag_s=4.0)
    assert both_in_range.found is False  # a genuine tie: ambiguous

    narrow = audio_sync.xcorr_lag(pattern, b, SR_LOW, max_lag_s=1.0)  # only the copy at +0.5 s is in range
    assert narrow.found is True
    assert abs(narrow.lag_s - 0.5) < 2e-3
    assert narrow.peak_ratio > 1.25


@pytest.mark.parametrize(("gap_s", "ambiguous"), [(0.15, False), (0.25, True)], ids=["gap_0.15s", "gap_0.25s"])
def test_t_sync_09_exclusion_radius_is_two_tenths_of_a_second(gap_s, ambiguous):
    """Catches: an exclusion radius far from 0.2 s: a second copy 0.15 s from the best does not count, 0.25 s does.

    The radius must stay below the gap of the two claps of a pair (0.3 s at the least): when only one clap of the
    pair is in view, the other clap is a second peak of almost the same height and the match must be refused, not
    accepted with the lag of the wrong clap (the adversarial pass found a radius of 0.5 s hiding it).
    """
    n_a = 1500
    pattern = _burst_pattern(n_a, SR_LOW, seed=3)
    b = np.zeros(5000)
    b[500 : 500 + n_a] += pattern
    shifted = 500 + int(gap_s * SR_LOW)
    b[shifted : shifted + n_a] += 0.97 * pattern  # a weaker copy: the stronger one is the best peak

    est = audio_sync.xcorr_lag(pattern, b, SR_LOW, max_lag_s=4.0)

    assert est.found is (not ambiguous), est


@pytest.mark.parametrize("bad", [float("nan"), float("inf")], ids=["nan", "inf"])
@pytest.mark.parametrize("where", ["a", "b"])
def test_t_sync_09_a_non_finite_envelope_is_not_found(bad, where):
    """Catches: NaN or inf reaching the correlation (a NaN peak breaks the schema): NaN means not observed."""
    a = _spike_array(3.0)
    b = a.copy()
    (a if where == "a" else b)[100] = bad

    est = audio_sync.xcorr_lag(a, b, SR_LOW, max_lag_s=1.0)

    assert est.found is False
    assert est.lag_s is None and est.t_match_s is None
    assert est.peak is None and est.peak_ratio is None


def test_t_sync_09_b_shorter_than_a_is_matched():
    """Catches: a matcher that assumes B is at least as long as A (the lag arithmetic changes when it is not)."""
    a = _gauss(3000, 1.2, SR_LOW, 0.01)
    b = _gauss(1800, 1.5, SR_LOW, 0.01)  # shorter, and the burst is 0.3 s later

    est = audio_sync.xcorr_lag(a, b, SR_LOW, max_lag_s=1.0)

    assert est.found is True
    assert abs(est.lag_s - 0.3) < 1e-3


def test_t_sync_09_a_window_rejected_by_the_ratio_gate_keeps_the_measured_values():
    """Catches: the measured peak and ratio thrown away for a rejected window (section 9.3 keeps them)."""
    pattern, b = _two_copies(1.0, 0.97)
    probe = _probe(pattern, b, SR_LOW, 4.0)

    est = audio_sync.xcorr_lag(pattern, b, SR_LOW, max_lag_s=4.0)

    assert est.found is False and est.lag_s is None and est.t_match_s is None
    assert est.peak == pytest.approx(probe.peak)
    assert est.peak_ratio == pytest.approx(probe.peak_ratio)


def test_t_sync_09_a_window_envelope_equals_the_envelope_of_the_whole_recording():
    """Catches: no filter context around a window (edge transients), or no zero-fill outside the audio.

    Tests the private ``_env_slice``: the envelope of a window cut from a longer recording must equal the envelope of
    the whole recording at the same samples (a burst 10 ms after the window start is the sensitive case), and
    positions outside the recording are 0 (no data there), not wrapped or filtered noise.
    """
    params = audio_sync.SyncAudioParams()
    sr = params.sr
    x = (0.002 * np.random.default_rng(3).standard_normal(20 * sr)).astype(np.float32)
    burst_len = int(0.005 * sr)
    burst = np.sin(2 * np.pi * 1200 * np.arange(burst_len) / sr) * np.exp(-np.linspace(0, 5, burst_len))
    start = int(10.01 * sr)
    x[start : start + burst_len] += burst.astype(np.float32)
    i0, i1 = 10 * sr, 13 * sr

    window = audio_sync._env_slice(x, i0, i1, params)
    whole = audio_sync.envelope(x, sr, hp_hz=params.hp_hz, lp_hz=params.lp_hz)[i0:i1]
    assert window.shape == whole.shape
    assert float(np.abs(window - whole).max()) <= 1e-6 * float(whole.max())

    overhang = audio_sync._env_slice(x, -sr, 2 * sr, params)  # one second before the recording starts
    assert overhang.shape == (3 * sr,)
    assert not overhang[:sr].any() and overhang[sr:].any()
    tail = audio_sync._env_slice(x, 19 * sr, 22 * sr, params)  # two seconds after the recording ends
    assert tail.shape == (3 * sr,) and not tail[sr:].any() and tail[:sr].any()


def test_t_sync_09_the_lag_range_is_centred_on_center_lag_s():
    """Catches: a centre that is ignored, or a lag range that stays centred on 0 whatever the centre (end window)."""
    a = _gauss(2000, 0.8, SR_LOW, 0.01)
    b = _gauss(8000, 4.3, SR_LOW, 0.01)  # B shows the burst 3.5 s later

    assert audio_sync.xcorr_lag(a, b, SR_LOW, max_lag_s=0.5).found is False  # centred on 0: the match is out of range
    centred = audio_sync.xcorr_lag(a, b, SR_LOW, max_lag_s=0.5, center_lag_s=3.4)
    assert centred.found is True
    assert abs(centred.lag_s - 3.5) < 1e-3  # the lag is still relative to the starts of the arrays, not to the centre
    too_narrow = audio_sync.xcorr_lag(a, b, SR_LOW, max_lag_s=0.05, center_lag_s=3.4)
    assert too_narrow.found is False  # a range narrower than the exclusion radius cannot show a unique peak
