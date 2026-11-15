"""T-SCH-01 (sync part): ``SyncManifest`` and the time mapping between two cameras (P2.01).

Convention (fixes the undefined ``t0`` of W2): times are seconds on each camera's own video timeline (seconds from
its first presentation timestamp). ``t_b = t_a + offset_s + drift * (t_a - t_ref_s)``; ``t_ref_s`` is the centre of the
matched start window on camera A; ``drift`` is dimensionless (1e-4 = 100 ppm). An unknown offset or drift is ``null``,
never 0.
"""

from __future__ import annotations

import copy

import numpy as np
import pytest

from taiji_ai.schemas._base import ManifestError, parse_manifest, read_manifest, write_manifest
from taiji_ai.schemas.sync import MAX_RESIDUAL_FRAMES, SyncManifest, SyncUnavailable

REC_A = "3f2b8c1e-5d4a-4e7b-9c1a-0b2d3e4f5a6b"
REC_B = "7a1c9d2e-8b3f-4c5d-a6e7-1f2a3b4c5d6e"


def _sync() -> dict:
    """A take synchronised by sound at both ends and checked with the flash: usable for metrics."""
    return {
        "schema_version": "sync/1",
        "take_id": "S01-P03-T02",
        "cam_a": "camA",
        "cam_b": "camB",
        "recording_id_a": REC_A,
        "recording_id_b": REC_B,
        "method": "audio_xcorr/1",
        "params": {"sample_rate_hz": 16000, "envelope_lp_hz": 50.0, "window_s": 30.0, "max_lag_s": 15.0},
        "start": {"window_a_s": [0.0, 30.0], "lag_s": 0.737, "peak": 0.93, "peak_ratio": 3.1, "found": True},
        "end": {"window_a_s": [340.0, 370.0], "lag_s": 0.7371, "peak": 0.91, "peak_ratio": 2.8, "found": True},
        "status": "ok",
        "not_found_reason": None,
        "offset_s": 0.737,
        "drift": 3.0e-6,
        "t_ref_s": 15.0,
        "validation": {
            "method": "flash",
            "flash_a_s": [3.2, 4.2, 360.1, 361.1],
            "flash_b_s": [3.9373, 4.9373, 360.8374, 361.8374],
            "residual_start_ms": 12.0,
            "residual_end_ms": 9.0,
            "residual_ms": 12.0,
            "residual_frames": 0.36,
            "frame_dt_s": 1 / 30,
        },
        "usable_for_metrics": True,
        "usable_reason": "usable",
        "created_at": "2026-11-20T09:20:00+07:00",
        "tools": {"ffprobe": "9.0.1", "pyav": "19.0.2", "taiji_ai": "0.1.0"},
    }


_NO_WINDOW = {"window_a_s": [0.0, 30.0], "lag_s": None, "peak": None, "peak_ratio": None, "found": False}
_NO_FLASH = {
    "method": "none",
    "flash_a_s": [],
    "flash_b_s": [],
    "residual_start_ms": None,
    "residual_end_ms": None,
    "residual_ms": None,
    "residual_frames": None,
    "frame_dt_s": None,
}


def _start_only() -> dict:
    d = _sync()
    d["end"] = {**_NO_WINDOW, "window_a_s": [340.0, 370.0]}
    d.update(status="start_only", drift=None, usable_for_metrics=False, usable_reason="start_only")
    d["validation"] = {**d["validation"], "residual_end_ms": None, "residual_ms": 12.0}
    return d


def _not_found() -> dict:
    d = _sync()
    d["start"] = copy.deepcopy(_NO_WINDOW)
    d["end"] = {**_NO_WINDOW, "window_a_s": [340.0, 370.0]}
    d.update(status="not_found", not_found_reason="clap_not_found", offset_s=None, drift=None, t_ref_s=None)
    d.update(usable_for_metrics=False, usable_reason="audio_not_found", validation=copy.deepcopy(_NO_FLASH))
    return d


def _set(d: dict, path: str, value) -> dict:
    d = copy.deepcopy(d)
    cur = d
    *head, last = path.split(".")
    for key in head:
        cur = cur[key]
    cur[last] = value
    return d


def _with(d: dict, **changes) -> dict:
    d = copy.deepcopy(d)
    d.update(changes)
    return d


# --- T-SCH-01a: round trip and the three statuses ---------------------------------------------------------------------


@pytest.mark.parametrize("make", [_sync, _start_only, _not_found], ids=["ok", "start-only", "not-found"])
def test_t_sch_01a_sync_manifest_round_trips_in_every_status(tmp_path, make):
    m = parse_manifest(SyncManifest, make())
    assert read_manifest(write_manifest(tmp_path / "takes" / "sync.json", m), SyncManifest) == m


# --- T-SCH-01e: rejected combinations --------------------------------------------------------------------------------


def _cases() -> list[tuple[str, dict, str]]:
    ok = _sync()
    return [
        ("not-found-with-offset", _with(_not_found(), offset_s=0.5), "offset_s"),
        ("not-found-with-drift", _with(_not_found(), drift=0.0), "drift"),
        ("not-found-without-reason", _with(_not_found(), not_found_reason=None), "not_found_reason"),
        ("ok-with-a-reason", _with(ok, not_found_reason="no_audio"), "not_found_reason"),
        ("start-only-with-drift", _with(_start_only(), drift=1e-6), "drift"),
        ("start-only-without-offset", _with(_start_only(), offset_s=None), "offset_s"),
        ("ok-without-drift", _with(ok, drift=None), "drift"),
        ("ok-without-offset", _with(ok, offset_s=None), "offset_s"),
        ("ok-without-t-ref", _with(ok, t_ref_s=None), "t_ref_s"),
        ("ok-but-end-not-found", _with(ok, end={**_NO_WINDOW, "window_a_s": [340.0, 370.0]}), "status"),
        (
            "start-only-but-both-found",
            _with(ok, status="start_only", drift=None, usable_for_metrics=False, usable_reason="start_only"),
            "status",
        ),
        ("not-found-but-start-found", _with(_not_found(), start=ok["start"]), "status"),
        ("usable-without-flash", _with(ok, validation=copy.deepcopy(_NO_FLASH)), "usable"),
        (
            "usable-residual-too-large",
            _set(
                _set(_set(ok, "validation.residual_start_ms", 34.0), "validation.residual_ms", 34.0),
                "validation.residual_frames",
                1.02,
            ),
            "usable",
        ),
        ("drift-minus-one-has-no-inverse", _with(ok, drift=-1.0), "drift"),
        ("usable-with-start-only", _with(_start_only(), usable_for_metrics=True, usable_reason="usable"), "usable"),
        ("reason-usable-but-false", _with(ok, usable_for_metrics=False), "usable"),
        ("true-with-another-reason", _with(ok, usable_reason="residual_too_large"), "usable"),
        ("cameras-not-sorted", _with(ok, cam_a="camB", cam_b="camA"), "cam_a"),
        ("same-camera", _with(ok, cam_b="camA"), "cam_a"),
        ("same-recording", _with(ok, recording_id_b=REC_A), "recording_id"),
        ("found-without-lag", _set(ok, "start.lag_s", None), "found"),
        ("found-false-with-lag", _set(_not_found(), "start.lag_s", 0.5), "found"),
        ("window-reversed", _set(ok, "start.window_a_s", [30.0, 0.0]), "window_a_s"),
        ("peak-above-one", _set(ok, "start.peak", 1.5), "peak"),
        ("peak-ratio-below-one", _set(ok, "start.peak_ratio", 0.5), "peak_ratio"),
        ("residual-frames-inconsistent", _set(ok, "validation.residual_frames", 0.9), "residual_frames"),
        ("residual-ms-not-the-larger-end", _set(ok, "validation.residual_ms", 5.0), "residual_ms"),
        (
            "flash-without-any-residual",
            _set(
                _set(_set(ok, "validation.residual_start_ms", None), "validation.residual_end_ms", None),
                "validation.residual_ms",
                None,
            ),
            "validation",
        ),
        (
            "none-with-a-residual",
            _set(_with(ok, validation=copy.deepcopy(_NO_FLASH)), "validation.residual_ms", 3.0),
            "validation",
        ),
        ("unknown-method", _with(ok, method="clap/9"), "method"),
        ("wrong-version", _with(ok, schema_version="sync/2"), "schema_version"),
        ("nan-offset", _with(ok, offset_s=float("nan")), "offset_s"),
        ("naive-created-at", _with(ok, created_at="2026-11-20T09:20:00"), "created_at"),
    ]


# The message of the rule that must reject the case. Matching only the field name is too weak: a neighbouring rule (or
# the crash of a removed rule) can mention the same field, and the test would pass for the wrong reason (BUG-0047).
_EXPECT = {
    "not-found-with-offset": "offset_s must be null",
    "not-found-with-drift": "drift must be null",
    "not-found-without-reason": "not_found_reason is required",
    "ok-with-a-reason": "not_found_reason must be null",
    "start-only-with-drift": "drift must be null",
    "start-only-without-offset": "offset_s is required",
    "ok-without-drift": "drift is required",
    "ok-without-offset": "offset_s is required",
    "ok-without-t-ref": "t_ref_s is required",
    "ok-but-end-not-found": "windows give 'start_only'",
    "start-only-but-both-found": "windows give 'ok'",
    "not-found-but-start-found": "windows give 'start_only'",
    "usable-without-flash": "needs a flash validation",
    "usable-residual-too-large": "at most 1.0 frame",
    "usable-with-start-only": "needs status 'ok'",
    "reason-usable-but-false": "exactly when usable_for_metrics",
    "true-with-another-reason": "exactly when usable_for_metrics",
    "cameras-not-sorted": "must sort before",
    "same-camera": "must sort before",
    "same-recording": "must differ",
    "found-without-lag": "found is true",
    "found-false-with-lag": "found is false",
    "residual-frames-inconsistent": "residual_frames must equal",
    "residual-ms-not-the-larger-end": "must be the larger",
    "flash-without-any-residual": "at least one end",
    "none-with-a-residual": "validation method is none",
}


@pytest.mark.parametrize(
    ("data", "expected"), [(d, _EXPECT.get(n, f)) for n, d, f in _cases()], ids=[n for n, _, _ in _cases()]
)
def test_t_sch_01e_invalid_combination_is_rejected_by_the_right_rule(data, expected):
    with pytest.raises(ManifestError, match=expected):
        parse_manifest(SyncManifest, data)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("take_id", "S01-P03"),
        ("take_id", "s01-p03-t02"),
        ("cam_a", "CAMA"),  # sorts before "camB", so only the pattern can reject it
        ("cam_a", "cam"),
        ("cam_b", "camera"),
        ("recording_id_a", "not-a-uuid"),
        ("recording_id_b", "7a1c9d2e-8b3f-1c5d-a6e7-1f2a3b4c5d6e"),  # version 1, not 4
    ],
)
def test_t_sch_01e_bad_identifier_is_rejected(path, value):
    with pytest.raises(ManifestError, match=f"{path}: String should match"):
        parse_manifest(SyncManifest, _with(_sync(), **{path: value}))


def test_t_sch_01e_the_usability_boundary_is_one_frame():
    assert MAX_RESIDUAL_FRAMES == 1.0
    edge = _set(_set(_sync(), "validation.residual_ms", 1000 / 30), "validation.residual_frames", 1.0)
    edge = _set(_set(edge, "validation.residual_start_ms", 1000 / 30), "validation.residual_end_ms", 5.0)
    assert parse_manifest(SyncManifest, edge).usable_for_metrics is True


def test_t_sch_01e_a_flash_found_only_at_the_start_is_kept_but_never_usable():
    """DEC-0025: the flash is needed at both ends. The missing end stays null (no made-up residual)."""
    d = _sync()
    d["validation"] = {**d["validation"], "residual_end_ms": None, "residual_ms": 12.0}
    with pytest.raises(ManifestError, match="both the start and the end"):
        parse_manifest(SyncManifest, d)  # still marked usable
    d.update(usable_for_metrics=False, usable_reason="flash_not_found")
    m = parse_manifest(SyncManifest, d)
    assert m.validation.residual_end_ms is None and m.usable_for_metrics is False


# --- T-SCH-01f: the time mapping --------------------------------------------------------------------------------------


def _mapped(offset: float, drift: float, t_ref: float) -> SyncManifest:
    d = _set(_set(_set(_sync(), "offset_s", offset), "drift", drift), "t_ref_s", t_ref)
    return parse_manifest(SyncManifest, d)


def test_t_sch_01f_sign_and_size_on_hand_made_examples():
    assert _mapped(0.5, 0.0, 5.0).a_to_b(10.0) == pytest.approx(10.5)  # B shows the same moment 0.5 s later
    assert _mapped(0.5, 1e-4, 5.0).a_to_b(15.0) == pytest.approx(15.0 + 0.5 + 1e-4 * 10.0)  # 15.501
    assert _mapped(0.5, 1e-4, 5.0).a_to_b(5.0) == pytest.approx(5.5)  # no drift contribution at t_ref
    assert _mapped(-0.25, 0.0, 5.0).b_to_a(10.0) == pytest.approx(10.25)
    assert _mapped(0.5, -1e-4, 5.0).a_to_b(15.0) == pytest.approx(15.0 + 0.5 - 1e-4 * 10.0)


@pytest.mark.parametrize("drift", [-1e-3, -1e-4, 0.0, 1e-4, 1e-3])
def test_t_sch_01f_a_to_b_and_b_to_a_are_exact_inverses(drift):
    m = _mapped(0.737, drift, 15.0)
    t = np.linspace(0.0, 400.0, 9)
    assert np.max(np.abs(m.b_to_a(m.a_to_b(t)) - t)) < 1e-9
    assert np.max(np.abs(m.a_to_b(m.b_to_a(t)) - t)) < 1e-9
    assert m.b_to_a(m.a_to_b(123.456)) == pytest.approx(123.456, abs=1e-9)


def test_t_sch_01f_a_scalar_stays_a_scalar_and_an_array_stays_an_array():
    m = _mapped(0.5, 0.0, 5.0)
    assert isinstance(m.a_to_b(1.0), float)
    assert isinstance(m.a_to_b(np.array([1.0, 2.0])), np.ndarray)


@pytest.mark.parametrize("make", [_start_only, _not_found], ids=["start-only", "not-found"])
def test_t_sch_01f_no_mapping_unless_both_ends_are_matched(make):
    m = parse_manifest(SyncManifest, make())
    with pytest.raises(SyncUnavailable, match="status"):
        m.a_to_b(1.0)
    with pytest.raises(SyncUnavailable, match="status"):
        m.b_to_a(1.0)
