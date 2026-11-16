"""Audio synchronization between two cameras using envelope cross-correlation (W2 steps 1-3, P2.04).

Given two recordings of one take (camera A is the reference, ``cam_a`` sorts before ``cam_b``), finds how far B's video
timeline is from A's at the start and at the end of the take, from the two claps of each sync signal, and says "not
found" instead of guessing.

Time convention (``schemas/sync.py``): seconds on each camera's **video** timeline; ``offset_s`` is B minus A at
``t_ref_s`` (positive: B shows the same moment later); ``drift`` is dimensionless. Inside this module the correlation
works on the **audio** timelines (seconds from the first audio sample) and converts with ``audio.start_offset_s`` of
each recording: ``t_video = t_audio + start_offset_s``.

Windows: the *start* window is the first ``window_s`` seconds of A matched against the first ``window_s + max_lag_s``
of B (the two phones are started by one person, so their start difference is seconds). The *end* window is the last
``window_s`` seconds of A, searched in B **where the start offset predicts it**, within a margin that covers the clock
drift the phones may have (``max_drift``); it does not depend on which phone was stopped first. If the start is not
found, the end is not searched (no offset to predict from). A drift above ``max_drift`` is not a clock: the end is then
rejected and the status is ``start_only``, so a wrong lag can never become ``ok``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import scipy.signal

from taiji_ai.io.audio import AUDIO_SAMPLE_RATE_HZ, AudioError, extract_audio, read_wav
from taiji_ai.schemas._base import ManifestError, read_manifest
from taiji_ai.schemas.recording import RecordingManifest
from taiji_ai.schemas.sync import SyncWindow

log = logging.getLogger(__name__)

# Engineering parameters (recorded in sync.json ``params``); none of them is a domain threshold (DEC-0031, DEC-0032).
DEFAULT_MIN_PEAK = 0.25  # normalised correlation of the best match
DEFAULT_MIN_PEAK_RATIO = 1.25  # best peak over the second best (outside the exclusion radius)
DEFAULT_MIN_CREST = 2.5  # max / mean of an envelope: a window without a transient is refused
DEFAULT_RATIO_FLOOR = 0.01  # a second peak below this counts as this value (the ratio is then at most peak / floor)
# [-] largest clock difference between two phones that is believed (500 ppm; phone clocks differ by tens of ppm).
# It is also the cross-check of the two measurements: an error E in either window shows as a drift E / dt, so a
# clap matched wrongly at one end is refused whenever E / dt exceeds it (a 1 s error up to a 2000 s take).
DEFAULT_MAX_DRIFT = 500e-6
# [s] search margin of the end window on top of the drift allowance. It must be wider than the gap of a clap pair (about
# 1 s, up to 2 s): when the true match lies just outside the plausible band, it is still the best peak of the search, is
# rejected by the drift limit, and a single clap of the pair cannot be matched inside the band instead (BUG-0058).
DEFAULT_END_MARGIN_S = 3.5
# [s] Guard zone of the START search: the start window is searched this much beyond ``max_lag_s`` and a lag beyond
# ``max_lag_s`` is then refused. Without it, a true match just outside the range is invisible and a single clap of
# the pair matches inside it (BUG-0058, found by the adversarial pass).
DEFAULT_START_GUARD_S = 3.5
# [s] around the best peak: the second peak is looked for outside it. It must be shorter than the gap of the two
# claps of a pair (0.3 s at the least): when only one clap of the pair is in view, the other clap of the pair is a
# second peak of almost the same height, the ratio is about 1 and the match is refused. A larger radius hid it.
EXCLUSION_RADIUS_S = 0.2
T_MATCH_MIN_SHARE = 0.05  # a product below this share of its maximum is noise, not evidence, for ``t_match_s``
ENVELOPE_CONTEXT_S = 2.0  # [s] of audio filtered around a window so that the filter edges stay outside it


class SyncError(AudioError):
    """``estimate_sync`` refuses its input."""


class TakeMismatch(SyncError):
    """The two recordings belong to different takes."""


class SyncInputError(SyncError):
    """A recording manifest cannot be read, or a cached ``audio.wav`` has an unexpected sample rate."""


@dataclass(frozen=True)
class LagEstimate:
    lag_s: float | None  # B minus A [s]; None when not found
    peak: float | None  # normalised correlation of the best match, clipped to [0, 1]
    peak_ratio: float | None  # best peak over the second best (floored), at least 1; None when not measurable
    found: bool
    t_match_s: float | None = (
        None  # [s] from the start of A's window: where the matched evidence is; None when not found
    )


@dataclass(frozen=True)
class SyncAudioParams:
    sr: int = AUDIO_SAMPLE_RATE_HZ
    hp_hz: float = 300.0
    lp_hz: float = 50.0
    window_s: float = 30.0
    max_lag_s: float = 15.0  # search range of the start window
    min_peak: float = DEFAULT_MIN_PEAK
    min_peak_ratio: float = DEFAULT_MIN_PEAK_RATIO
    min_crest: float = DEFAULT_MIN_CREST
    max_drift: float = DEFAULT_MAX_DRIFT
    end_margin_s: float = DEFAULT_END_MARGIN_S
    start_guard_s: float = DEFAULT_START_GUARD_S
    ratio_floor: float = DEFAULT_RATIO_FLOOR

    def to_record(self) -> dict[str, float | int | str]:
        """The values written to ``params`` of the result and of ``sync.json``."""
        return {
            "sample_rate": self.sr,
            "hp_hz": self.hp_hz,
            "lp_hz": self.lp_hz,
            "window_s": self.window_s,
            "max_lag_s": self.max_lag_s,
            "min_peak": self.min_peak,
            "min_peak_ratio": self.min_peak_ratio,
            "min_crest": self.min_crest,
            "max_drift_ppm": self.max_drift * 1e6,
            "end_margin_s": self.end_margin_s,
            "start_guard_s": self.start_guard_s,
            "ratio_floor": self.ratio_floor,
        }


@dataclass(frozen=True)
class AudioSyncResult:
    cam_a: str
    cam_b: str
    recording_id_a: str
    recording_id_b: str
    start: SyncWindow
    end: SyncWindow
    status: Literal["ok", "start_only", "not_found"]
    not_found_reason: Literal["no_audio", "clap_not_found"] | None
    offset_s: float | None  # [s] at t_ref_s, on the video timelines
    drift: float | None  # [-]
    t_ref_s: float | None  # [s] on A's video timeline: where the start claps are
    params: dict[str, float | int | str]


def envelope(
    x: np.ndarray,
    sr: int,
    hp_hz: float = 300.0,
    lp_hz: float = 50.0,
) -> np.ndarray:
    """Energy envelope of an audio signal: high-pass, rectify, low-pass (zero-phase)."""
    if x.size < 64:
        return np.abs(x).astype(np.float32)

    # High pass to eliminate low-frequency rumble and hum
    sos_hp = scipy.signal.butter(4, hp_hz, btype="high", fs=sr, output="sos")
    x_hp = scipy.signal.sosfiltfilt(sos_hp, x)

    # Rectification, then low pass to smooth the envelope
    sos_lp = scipy.signal.butter(4, lp_hz, btype="low", fs=sr, output="sos")
    env = scipy.signal.sosfiltfilt(sos_lp, np.abs(x_hp))
    return np.maximum(env, 0.0).astype(np.float32)


def xcorr_lag(
    env_a: np.ndarray,
    env_b: np.ndarray,
    sr: int,
    max_lag_s: float = 15.0,
    min_peak: float = DEFAULT_MIN_PEAK,
    min_peak_ratio: float = DEFAULT_MIN_PEAK_RATIO,
    min_crest: float = DEFAULT_MIN_CREST,
    ratio_floor: float = DEFAULT_RATIO_FLOOR,
    center_lag_s: float = 0.0,
) -> LagEstimate:
    """Lag of envelope B against envelope A [s] (positive: B shows the event later), with a sub-sample peak.

    Lags are searched within ``max_lag_s`` of ``center_lag_s``; the lag returned is relative to the starts of the two
    arrays, like the centre.

    Zero-mean normalised cross-correlation (the rectified noise floor is a pedestal that would flatten the peak).
    The match is *found* only when the best peak is at least ``min_peak`` and exceeds the second best peak (outside
    ``EXCLUSION_RADIUS_S`` of the best) by ``min_peak_ratio``; both envelopes must also hold a transient (crest factor
    of at least ``min_crest``). A second peak below ``ratio_floor`` counts as ``ratio_floor``, so the ratio of a unique
    peak is finite. A window too short to hold a second peak cannot show that the match is unique: not found.
    """
    nothing = LagEstimate(lag_s=None, peak=None, peak_ratio=None, found=False)
    if env_a.size == 0 or env_b.size == 0:
        return nothing

    a = np.asarray(env_a, dtype=np.float64)
    b = np.asarray(env_b, dtype=np.float64)
    if not (np.isfinite(a).all() and np.isfinite(b).all()):
        return (
            nothing  # NaN or inf is "not observed" (AGENTS.md section 5.1): no peak, no lag, never a NaN in a manifest
        )
    mean_a, mean_b = float(np.mean(a)), float(np.mean(b))
    crest_a = float(np.max(a)) / mean_a if mean_a > 1e-12 else 0.0
    crest_b = float(np.max(b)) / mean_b if mean_b > 1e-12 else 0.0
    if crest_a < min_crest or crest_b < min_crest:
        return nothing

    a_zm = a - mean_a
    b_zm = b - mean_b
    norm_a = float(np.sum(a_zm**2))
    norm_b = float(np.sum(b_zm**2))
    if norm_a <= 1e-12 or norm_b <= 1e-12:
        return nothing

    # Correlate B against A: a peak at lag k where B[n + k] aligns with A[n].
    corr = scipy.signal.correlate(b_zm, a_zm, method="fft")
    lags = scipy.signal.correlation_lags(len(b_zm), len(a_zm))
    valid = np.abs(lags - int(round(center_lag_s * sr))) <= int(max_lag_s * sr)
    if not np.any(valid):
        return nothing
    norm_corr = corr[valid] / np.sqrt(norm_a * norm_b)
    lags_valid = lags[valid]

    peak_idx = int(np.argmax(norm_corr))
    best_lag = int(lags_valid[peak_idx])
    best_peak = float(norm_corr[peak_idx])
    peak = min(max(best_peak, 0.0), 1.0)  # rounding can give 1.0000000000000002; the schema refuses it

    # Second peak outside the exclusion radius of the best one.
    outside = np.abs(lags_valid - best_lag) > int(EXCLUSION_RADIUS_S * sr)
    if best_peak <= 0.0 or not np.any(outside):
        return LagEstimate(lag_s=None, peak=peak, peak_ratio=None, found=False)
    second = float(np.max(norm_corr[outside]))
    ratio = max(1.0, best_peak / max(second, ratio_floor))

    if not (best_peak >= min_peak and ratio >= min_peak_ratio):
        return LagEstimate(lag_s=None, peak=peak, peak_ratio=ratio, found=False)

    # Parabolic interpolation through the three samples around the integer peak.
    delta = 0.0
    if 0 < peak_idx < len(norm_corr) - 1:
        y_m1, y_0, y_p1 = (float(norm_corr[peak_idx + k]) for k in (-1, 0, 1))
        denom = y_m1 - 2.0 * y_0 + y_p1
        if abs(denom) > 1e-12:
            delta = (y_m1 - y_p1) / (2.0 * denom)
    lag_s = (best_lag + delta) / float(sr)

    return LagEstimate(
        lag_s=float(lag_s),
        peak=peak,
        peak_ratio=float(ratio),
        found=True,
        t_match_s=_matched_position(a_zm, b_zm, best_lag, sr),
    )


def _matched_position(a_zm: np.ndarray, b_zm: np.ndarray, lag: int, sr: int) -> float:
    """Centroid [s from the start of A] of A times B aligned at ``lag``: where the matched evidence is.

    Only the positive part of the product that reaches ``T_MATCH_MIN_SHARE`` of its maximum counts: the product of
    two independent noise envelopes is positive about half of the time and would pull the centroid to the middle of
    the window.
    """
    i0 = max(0, -lag)
    i1 = min(len(a_zm), len(b_zm) - lag)
    if i1 <= i0:
        return len(a_zm) / 2.0 / sr
    product = np.maximum(a_zm[i0:i1] * b_zm[i0 + lag : i1 + lag], 0.0)
    product[product < T_MATCH_MIN_SHARE * float(product.max(initial=0.0))] = 0.0
    total = float(product.sum())
    if total <= 0.0:
        return (i0 + i1) / 2.0 / sr
    return (i0 + float(np.dot(np.arange(i1 - i0), product)) / total) / sr


def _env_slice(samples: np.ndarray, i0: int, i1: int, params: SyncAudioParams) -> np.ndarray:
    """Envelope of ``samples[i0:i1]``; positions outside the recording are 0 (no data there).

    Only the slice and ``ENVELOPE_CONTEXT_S`` around it are filtered, never the whole recording.
    """
    n = int(samples.size)
    out = np.zeros(max(0, i1 - i0), dtype=np.float32)
    lo, hi = max(i0, 0), min(i1, n)
    if hi <= lo:
        return out
    ctx = int(ENVELOPE_CONTEXT_S * params.sr)
    c0, c1 = max(0, lo - ctx), min(n, hi + ctx)
    env = envelope(samples[c0:c1], params.sr, hp_hz=params.hp_hz, lp_hz=params.lp_hz)
    out[lo - i0 : hi - i0] = env[lo - c0 : hi - c0]
    return out


def _geometry(dur_a: float, dur_b: float, params: SyncAudioParams) -> tuple[float, float, float]:
    """Lengths [s]: (A's windows, B's start window, start of A's end window); short takes use 45 % of the take."""
    short = dur_a < params.window_s * 2.0
    win_a = min(params.window_s, dur_a * 0.45 if short else params.window_s)
    search = params.max_lag_s + params.start_guard_s
    b_start = min(win_a + search, dur_b * 0.5 if dur_b < params.window_s * 2.0 else dur_b - win_a)
    return win_a, b_start, max(win_a, dur_a - win_a)


def _video_window(t0: float, t1: float, start_offset_a: float) -> tuple[float, float]:
    """A window on A's audio timeline as a window on A's video timeline (``t_video = t_audio + start_offset``)."""
    lo = max(0.0, t0 + start_offset_a)
    return lo, max(t1 + start_offset_a, lo + 1e-6)


def _not_searched(window: tuple[float, float]) -> SyncWindow:
    return SyncWindow(window_a_s=window, lag_s=None, peak=None, peak_ratio=None, found=False)


def _read_manifests(path_a: Path, path_b: Path) -> tuple[RecordingManifest, RecordingManifest]:
    try:
        return (
            read_manifest(path_a / "recording.json", RecordingManifest),
            read_manifest(path_b / "recording.json", RecordingManifest),
        )
    except (OSError, ManifestError) as exc:
        raise SyncInputError("could not read the recording manifest of a camera") from exc


def estimate_sync(
    rec_dir_a: Path | str,
    rec_dir_b: Path | str,
    *,
    params: SyncAudioParams | None = None,
) -> AudioSyncResult:
    """Estimate the time offset and the clock drift between two cameras of the same take.

    Raises:
        TakeMismatch: the recordings belong to different takes.
        SyncInputError: a manifest cannot be read, or an ``audio.wav`` has another sample rate than ``params.sr``.
        AudioError: the audio cannot be extracted or read.
    """
    params = params or SyncAudioParams()
    path_a = Path(rec_dir_a).resolve()
    path_b = Path(rec_dir_b).resolve()
    man_a, man_b = _read_manifests(path_a, path_b)

    if man_a.take_id != man_b.take_id:
        raise TakeMismatch(f"the recordings belong to different takes: {man_a.take_id} and {man_b.take_id}")
    if man_a.camera_id == man_b.camera_id or man_a.recording_id == man_b.recording_id:
        raise SyncInputError("the two recordings are the same camera of the take: a sync needs two cameras")

    # Camera A is the reference (cam_a sorts before cam_b)
    if man_a.camera_id > man_b.camera_id:
        path_a, path_b = path_b, path_a
        man_a, man_b = man_b, man_a

    def result(
        start: SyncWindow,
        end: SyncWindow,
        status: Literal["ok", "start_only", "not_found"],
        reason: Literal["no_audio", "clap_not_found"] | None = None,
        offset_s: float | None = None,
        drift: float | None = None,
        t_ref_s: float | None = None,
    ) -> AudioSyncResult:
        return AudioSyncResult(
            cam_a=man_a.camera_id,
            cam_b=man_b.camera_id,
            recording_id_a=man_a.recording_id,
            recording_id_b=man_b.recording_id,
            start=start,
            end=end,
            status=status,
            not_found_reason=reason,
            offset_s=offset_s,
            drift=drift,
            t_ref_s=t_ref_s,
            params=params.to_record(),
        )

    if man_a.audio is None or man_b.audio is None:
        # The windows that would have been searched, from the container duration (nothing was observed in them).
        dur = man_a.duration_s if man_a.duration_s and man_a.duration_s > 0 else params.window_s * 2.0
        win_a, _, t0_end = _geometry(dur, dur, params)
        return result(
            _not_searched(_video_window(0.0, win_a, 0.0)),
            _not_searched(_video_window(t0_end, dur, 0.0)),
            "not_found",
            "no_audio",
        )

    samples_a, sr_a = read_wav(extract_audio(path_a))
    samples_b, sr_b = read_wav(extract_audio(path_b))
    if sr_a != params.sr or sr_b != params.sr:
        raise SyncInputError(
            f"audio.wav has the sample rate {sr_a} Hz (A) and {sr_b} Hz (B), expected {params.sr} Hz: "
            "delete the audio.wav files so that they are extracted again"
        )

    sr = params.sr
    n_a = int(samples_a.size)
    dur_a, dur_b = n_a / sr, samples_b.size / sr
    s_a, s_b = man_a.audio.start_offset_s, man_b.audio.start_offset_s
    av = s_b - s_a  # video-time lag = audio-time lag + av
    win_a, b_start_len, t0_end_a = _geometry(dur_a, dur_b, params)

    # 1. Start window
    start_est = xcorr_lag(
        _env_slice(samples_a, 0, int(win_a * sr), params),
        _env_slice(samples_b, 0, int(b_start_len * sr), params),
        sr,
        max_lag_s=params.max_lag_s + params.start_guard_s,  # wider than what is accepted, see DEFAULT_START_GUARD_S
        min_peak=params.min_peak,
        min_peak_ratio=params.min_peak_ratio,
        min_crest=params.min_crest,
        ratio_floor=params.ratio_floor,
    )
    start_window = _video_window(0.0, win_a, s_a)
    end_window = _video_window(t0_end_a, dur_a, s_a)  # until the start offset is known: A's last window

    if (
        not start_est.found
        or start_est.lag_s is None
        or start_est.t_match_s is None
        or abs(start_est.lag_s) > params.max_lag_s  # found in the guard zone: a start difference beyond the range
    ):
        start_win = SyncWindow(
            window_a_s=start_window, lag_s=None, peak=start_est.peak, peak_ratio=start_est.peak_ratio, found=False
        )
        log.info(
            "sync of take %s (%s vs %s): the start claps were not found",
            man_a.take_id,
            man_a.camera_id,
            man_b.camera_id,
        )
        return result(start_win, _not_searched(end_window), "not_found", "clap_not_found")

    lag0 = start_est.lag_s
    start_lag_video = lag0 + av
    t_ref_start = start_est.t_match_s + s_a  # A's video timeline
    start_win = SyncWindow(
        window_a_s=start_window,
        lag_s=start_lag_video,
        peak=start_est.peak,
        peak_ratio=start_est.peak_ratio,
        found=True,
    )

    # 2. End window: the last ``win_a`` seconds of the stretch BOTH cameras recorded (A's audio time up to
    #    ``dur_b - lag0``), so that the end claps are never at the edge of the window whichever phone stopped first;
    #    predicted in B from the start offset, within a margin that covers the drift a clock may have.
    t_end = min(dur_a, dur_b - lag0)
    t0_end_a = max(win_a, t_end - win_a)
    end_window = _video_window(t0_end_a, max(t_end, t0_end_a), s_a)
    i0_a, i1_a = int(round(t0_end_a * sr)), int(round(t_end * sr))
    dt_est = max(0.0, (t0_end_a + t_end) / 2.0 - (t_ref_start - s_a))
    margin = params.end_margin_s + params.max_drift * dt_est
    # B's slice is A's window moved by lag0 and widened by the margin on both sides (so that a clap pushed by the
    # drift is not cut off by the edge of the slice), cut to what B recorded: no zero fill, no step in the data.
    slice_start = int(round((t0_end_a + lag0 - margin) * sr))
    slice_end = int(round((t_end + lag0 + margin) * sr))
    i0_b, i1_b = max(0, slice_start), min(samples_b.size, slice_end)
    centre_s = (int(round((t0_end_a + lag0) * sr)) - i0_b) / sr  # where the prediction puts A's window in the slice
    end_est = xcorr_lag(
        _env_slice(samples_a, i0_a, i1_a, params),
        _env_slice(samples_b, i0_b, max(i0_b, i1_b), params),
        sr,
        max_lag_s=margin,
        center_lag_s=centre_s,
        min_peak=params.min_peak,
        min_peak_ratio=params.min_peak_ratio,
        min_crest=params.min_crest,
        ratio_floor=params.ratio_floor,
    )

    drift: float | None = None
    end_lag_video: float | None = None
    if end_est.found and end_est.lag_s is not None and end_est.t_match_s is not None:
        # xcorr lag is relative to the slice starts: B's slice starts at i0_b / sr, A's window at t0_end_a
        end_lag_video = end_est.lag_s + (i0_b / sr - i0_a / sr) + av
        t_ref_end = i0_a / sr + end_est.t_match_s + s_a
        dt = t_ref_end - t_ref_start
        if dt > 0.0:
            drift = (end_lag_video - start_lag_video) / dt
        if drift is None or abs(drift) > params.max_drift:
            log.warning(
                "sync of take %s: the end claps give a drift beyond %.0f ppm: not accepted (start only)",
                man_a.take_id,
                params.max_drift * 1e6,
            )
            end_lag_video, drift = None, None

    end_win = SyncWindow(
        window_a_s=end_window,
        lag_s=end_lag_video,
        peak=end_est.peak,
        peak_ratio=end_est.peak_ratio,
        found=end_lag_video is not None,
    )
    status: Literal["ok", "start_only"] = "ok" if end_win.found else "start_only"
    log.info(
        "sync of take %s (%s vs %s): status=%s, offset=%.6f s, drift=%s",
        man_a.take_id,
        man_a.camera_id,
        man_b.camera_id,
        status,
        start_lag_video,
        None if drift is None else f"{drift * 1e6:.1f} ppm",
    )
    return result(start_win, end_win, status, None, start_lag_video, drift, t_ref_start)
