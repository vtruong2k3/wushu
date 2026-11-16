"""Sync usability decision rule (W2 step 5, P2.06).

Combines the audio synchronization result (P2.04) and flash validation (P2.05) into
a single boolean decision (usable_for_metrics) and a documented reason (usable_reason).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from taiji_ai.schemas.sync import MAX_RESIDUAL_FRAMES, SyncValidation

if TYPE_CHECKING:
    from taiji_ai.io.audio_sync import AudioSyncResult

UsableReason = Literal[
    "usable",
    "no_audio",
    "audio_not_found",
    "start_only",
    "flash_not_found",
    "residual_too_large",
]


def decide_usability(
    audio: AudioSyncResult,
    validation: SyncValidation,
    *,
    max_residual_frames: float = MAX_RESIDUAL_FRAMES,
) -> tuple[bool, UsableReason]:
    """Decide whether two cameras may be combined in biomechanical metrics.

    Args:
        audio: Audio synchronization result from :func:`taiji_ai.io.audio_sync.estimate_sync`.
        validation: Flash validation result from :func:`taiji_ai.io.flash.validate_sync`.
        max_residual_frames: Maximum allowable residual in frames of the slower camera (default 1.0).

    Returns:
        (usable_for_metrics, usable_reason)
    """
    if audio.status == "not_found":
        if audio.not_found_reason == "no_audio":
            return False, "no_audio"
        return False, "audio_not_found"

    if audio.status == "start_only":
        return False, "start_only"

    # audio.status is "ok"
    if validation.method != "flash":
        return False, "flash_not_found"

    if validation.residual_start_ms is None or validation.residual_end_ms is None:
        return False, "flash_not_found"

    if validation.residual_frames is None:
        return False, "flash_not_found"

    if validation.residual_frames > max_residual_frames:
        return False, "residual_too_large"

    return True, "usable"
