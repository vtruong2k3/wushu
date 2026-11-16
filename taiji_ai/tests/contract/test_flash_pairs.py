"""T-SYNC-04f: the flash check refuses a mapping wrong by one pair gap, also when a flash is not seen (X.23, BUG-0064).

Each case makes a take with known flashes and claps (``helpers.flash_media``), runs the real audio sync, then gives
``validate_sync`` an offset that is wrong by a chosen amount (``dataclasses.replace`` of the audio result) and
``decide_usability`` decides. A mapping wrong by 1 s must never be usable.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from helpers.flash_media import PAIRS_A, make_flash_take
from helpers.sync_media import FFMPEG
from taiji_ai.config import Settings
from taiji_ai.io.audio_sync import estimate_sync
from taiji_ai.io.flash import validate_sync
from taiji_ai.io.sync_rule import decide_usability

pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not available")

DELTA_S = 0.5
FULL = PAIRS_A
FIRST_OF_EACH_PAIR = (PAIRS_A[0], PAIRS_A[2])
SECOND_OF_EACH_PAIR = (PAIRS_A[1], PAIRS_A[3])
START_PAIR_ONLY_FIRST = (
    PAIRS_A[0],
    PAIRS_A[2],
    PAIRS_A[3],
)  # the end pair is whole, the start pair loses its second flash
END_PAIR_ONLY_FIRST = (
    PAIRS_A[0],
    PAIRS_A[1],
    PAIRS_A[2],
)  # the start pair is whole, the end pair loses its second flash


def _shift(times: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(t + DELTA_S for t in times)


CASES = [
    # id, flashes of A, flashes of B (None: all, moved by delta), wrong_s, usable, reason
    pytest.param(FULL, None, 0.0, True, "usable", id="control_right_offset_every_flash_seen"),
    pytest.param(FULL, None, 1.0, False, "residual_too_large", id="plus_1s_every_flash_seen"),
    pytest.param(FULL, None, -1.0, False, "residual_too_large", id="minus_1s_every_flash_seen"),
    pytest.param(FIRST_OF_EACH_PAIR, None, 1.0, False, "flash_not_found", id="plus_1s_a_shows_only_the_first_flashes"),
    pytest.param(
        SECOND_OF_EACH_PAIR, None, -1.0, False, "flash_not_found", id="minus_1s_a_shows_only_the_second_flashes"
    ),
    pytest.param(FULL, _shift(FIRST_OF_EACH_PAIR), 1.0, False, "flash_not_found", id="plus_1s_b_shows_only_the_first"),
    pytest.param(END_PAIR_ONLY_FIRST, None, 1.0, False, "flash_not_found", id="plus_1s_only_the_end_pair_is_damaged"),
    pytest.param(
        START_PAIR_ONLY_FIRST, None, 1.0, False, "flash_not_found", id="plus_1s_only_the_start_pair_is_damaged"
    ),
    # An unmatched flash is not a pass, even when the offset is right: the take must be shot again (capture protocol).
    pytest.param(
        FIRST_OF_EACH_PAIR, None, 0.0, False, "flash_not_found", id="right_offset_a_shows_only_the_first_flashes"
    ),
    # A flash of A and B each hidden, a different one on each camera: the counts agree, the flashes are different ones.
    pytest.param(
        FIRST_OF_EACH_PAIR,
        _shift(SECOND_OF_EACH_PAIR),
        1.0,
        False,
        "flash_not_found",
        id="plus_1s_each_camera_shows_a_different_flash",
    ),
]


@pytest.mark.parametrize(("flashes_a", "flashes_b", "wrong_s", "usable", "reason"), CASES)
def test_t_sync_04f_a_wrong_mapping_is_never_usable(
    tmp_path: Path,
    ingest_settings: Settings,
    flashes_a: tuple[float, ...],
    flashes_b: tuple[float, ...] | None,
    wrong_s: float,
    usable: bool,
    reason: str,
):
    dir_a, dir_b = make_flash_take(tmp_path / "take", ingest_settings, flashes_a=flashes_a, flashes_b=flashes_b)
    audio = estimate_sync(dir_a, dir_b)
    assert audio.status == "ok", (
        f"the audio sync of the fixture must be ok, got {audio.status} ({audio.not_found_reason})"
    )
    assert audio.offset_s is not None and abs(audio.offset_s - DELTA_S) < 0.005

    given = replace(audio, offset_s=audio.offset_s + wrong_s)
    validation = validate_sync(given, dir_a, dir_b)
    decided, why = decide_usability(given, validation)

    assert (decided, why) == (usable, reason), (
        f"flashes seen A {len(validation.flash_a_s)} / B {len(validation.flash_b_s)}, "
        f"residual {validation.residual_ms} ms, usable={decided} ({why})"
    )
    if usable:
        assert validation.residual_frames is not None and validation.residual_frames <= 1.0
