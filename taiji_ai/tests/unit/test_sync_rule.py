"""T-SYNC-05, T-SYNC-05b: Sync usability rule tests (W2 step 5, P2.06)."""

from __future__ import annotations

import pytest

from taiji_ai.io.audio_sync import AudioSyncResult
from taiji_ai.io.sync_rule import decide_usability
from taiji_ai.schemas.sync import SyncValidation, SyncWindow


def _make_audio_result(
    status: str = "ok",
    not_found_reason: str | None = None,
) -> AudioSyncResult:
    win = SyncWindow(
        window_a_s=(0.0, 10.0),
        lag_s=0.5 if status in ("ok", "start_only") else None,
        peak=0.9 if status in ("ok", "start_only") else None,
        peak_ratio=2.0 if status in ("ok", "start_only") else None,
        found=status in ("ok", "start_only"),
    )
    end_win = SyncWindow(
        window_a_s=(50.0, 60.0),
        lag_s=0.5 if status == "ok" else None,
        peak=0.9 if status == "ok" else None,
        peak_ratio=2.0 if status == "ok" else None,
        found=status == "ok",
    )
    return AudioSyncResult(
        cam_a="camA",
        cam_b="camB",
        recording_id_a="11111111-1111-4111-8111-111111111111",
        recording_id_b="22222222-2222-4222-8222-222222222222",
        start=win,
        end=end_win,
        status=status,  # type: ignore[arg-type]
        not_found_reason=not_found_reason,  # type: ignore[arg-type]
        offset_s=0.5 if status in ("ok", "start_only") else None,
        drift=0.0001 if status == "ok" else None,
        t_ref_s=5.0 if status in ("ok", "start_only") else None,
        params={},
    )


def _make_validation(
    method: str = "flash",
    residual_frames: float | None = 0.5,
    start_ms: float | None = None,
    end_ms: float | None = None,
    frame_dt_s: float | None = 1.0 / 30.0,
) -> SyncValidation:
    if method == "none":
        return SyncValidation(
            method="none",
            flash_a_s=(),
            flash_b_s=(),
            residual_start_ms=None,
            residual_end_ms=None,
            residual_ms=None,
            residual_frames=None,
            frame_dt_s=None,
        )
    if start_ms is None and end_ms is None:
        if residual_frames is not None and frame_dt_s is not None:
            calc_ms = float(residual_frames * 1000.0 * frame_dt_s)
            start_ms = calc_ms
            end_ms = calc_ms
            res_ms = calc_ms
            res_frames = residual_frames
        else:
            res_ms = None
            res_frames = None
    else:
        ends = [r for r in (start_ms, end_ms) if r is not None]
        res_ms = max(ends) if ends else None
        res_frames = (
            (res_ms / 1000.0 / frame_dt_s) if (res_ms is not None and frame_dt_s is not None) else residual_frames
        )
    return SyncValidation(
        method="flash",
        flash_a_s=(1.0, 50.0),
        flash_b_s=(1.5, 50.5),
        residual_start_ms=start_ms,
        residual_end_ms=end_ms,
        residual_ms=res_ms,
        residual_frames=res_frames,
        frame_dt_s=frame_dt_s,
    )


def test_t_sync_05_threshold_boundary():
    """T-SYNC-05: residual <= 1.0 frame is usable; residual > 1.0 frame is residual_too_large."""
    audio = _make_audio_result(status="ok")

    # Exactly 1.0 frame -> usable
    val_1_0 = _make_validation(residual_frames=1.0)
    usable, reason = decide_usability(audio, val_1_0)
    assert usable is True
    assert reason == "usable"

    # 0.99 frame -> usable
    val_0_99 = _make_validation(residual_frames=0.99)
    usable, reason = decide_usability(audio, val_0_99)
    assert usable is True
    assert reason == "usable"

    # 1.0001 frame -> residual_too_large
    val_1_0001 = _make_validation(residual_frames=1.0001)
    usable, reason = decide_usability(audio, val_1_0001)
    assert usable is False
    assert reason == "residual_too_large"

    # 1.01 frame -> residual_too_large
    val_1_01 = _make_validation(residual_frames=1.01)
    usable, reason = decide_usability(audio, val_1_01)
    assert usable is False
    assert reason == "residual_too_large"


@pytest.mark.parametrize(
    (
        "status",
        "not_found_reason",
        "val_method",
        "start_ms",
        "end_ms",
        "res_frames",
        "expected_usable",
        "expected_reason",
    ),
    [
        ("not_found", "no_audio", "none", None, None, None, False, "no_audio"),
        ("not_found", "clap_not_found", "none", None, None, None, False, "audio_not_found"),
        ("start_only", None, "none", None, None, None, False, "start_only"),
        ("start_only", None, "flash", 10.0, None, 0.3, False, "start_only"),
        ("ok", None, "none", None, None, None, False, "flash_not_found"),
        ("ok", None, "flash", 10.0, None, 0.3, False, "flash_not_found"),
        ("ok", None, "flash", None, 10.0, 0.3, False, "flash_not_found"),
        ("ok", None, "flash", 50.0, 50.0, 1.5, False, "residual_too_large"),
        ("ok", None, "flash", 10.0, 15.0, 0.45, True, "usable"),
    ],
)
def test_t_sync_05b_reasons(
    status: str,
    not_found_reason: str | None,
    val_method: str,
    start_ms: float | None,
    end_ms: float | None,
    res_frames: float | None,
    expected_usable: bool,
    expected_reason: str,
):
    """T-SYNC-05b: each other condition gives false with the expected reason."""
    audio = _make_audio_result(status=status, not_found_reason=not_found_reason)
    val = _make_validation(
        method=val_method,
        residual_frames=res_frames,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    usable, reason = decide_usability(audio, val)
    assert usable == expected_usable
    assert reason == expected_reason
