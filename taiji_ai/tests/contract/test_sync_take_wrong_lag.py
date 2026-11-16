"""T-SYNC-05e: ``sync_take`` never marks a take usable when the audio lag is wrong by one second (BUG-0063, BUG-0064).

The audio result is forced wrong by +1 s (the outcome of a clap pair that is damaged the same way at both ends,
BUG-0063: ``status = ok``, both windows agree) after the real audio sync ran on a real container. Everything else is
real: the flash video, ``validate_sync``, ``decide_usability``, ``sync.json`` written and read back.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest

from helpers.flash_media import PAIRS_A, make_flash_take
from helpers.sync_media import FFMPEG
from taiji_ai.config import Settings
from taiji_ai.io import audio_sync as audio_sync_module
from taiji_ai.pipeline import sync_take as sync_take_module
from taiji_ai.pipeline.sync_take import sync_take
from taiji_ai.schemas._base import read_manifest
from taiji_ai.schemas.sync import SyncManifest
from taiji_ai.store.db import connect
from taiji_ai.store.sync import find_sync

pytestmark = [pytest.mark.skipif(not FFMPEG, reason="ffmpeg not available"), pytest.mark.usefixtures("clean_logging")]

TAKE_ID = "S01-P03-T01"
FIRST_OF_EACH_PAIR = (PAIRS_A[0], PAIRS_A[2])


@pytest.mark.parametrize(
    ("flashes_a", "wrong_s", "usable", "reason"),
    [
        pytest.param(PAIRS_A, 0.0, True, "usable", id="control_right_offset"),
        pytest.param(PAIRS_A, 1.0, False, "residual_too_large", id="audio_plus_1s_every_flash_seen"),
        pytest.param(PAIRS_A, -1.0, False, "residual_too_large", id="audio_minus_1s_every_flash_seen"),
        pytest.param(
            FIRST_OF_EACH_PAIR, 1.0, False, "flash_not_found", id="audio_plus_1s_a_hides_a_flash_of_each_pair"
        ),
    ],
)
def test_t_sync_05e_sync_json_of_a_wrong_audio_lag_is_not_usable(
    tmp_path: Path,
    ingest_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    flashes_a: tuple[float, ...],
    wrong_s: float,
    usable: bool,
    reason: str,
):
    make_flash_take(tmp_path / "take", ingest_settings, flashes_a=flashes_a, take_id=TAKE_ID)

    def estimate_with_a_wrong_lag(dir_a: Path, dir_b: Path):
        result = audio_sync_module.estimate_sync(dir_a, dir_b)
        assert result.status == "ok" and result.offset_s is not None, "the fixture's audio sync must be ok first"
        return replace(result, offset_s=result.offset_s + wrong_s)

    monkeypatch.setattr(sync_take_module, "estimate_sync", estimate_with_a_wrong_lag)

    manifest = sync_take(TAKE_ID, settings=ingest_settings)

    assert manifest.status == "ok"  # sound alone was fooled, that is the point of the test
    assert (manifest.usable_for_metrics, manifest.usable_reason) == (usable, reason)
    on_disk = read_manifest(ingest_settings.data_dir / "takes" / TAKE_ID / "sync.json", SyncManifest)
    assert (on_disk.usable_for_metrics, on_disk.usable_reason) == (usable, reason)
    if reason == "residual_too_large":
        assert on_disk.validation.residual_frames is not None and on_disk.validation.residual_frames > 1.0
    if reason == "flash_not_found":
        assert on_disk.validation.residual_start_ms is None or on_disk.validation.residual_end_ms is None


def _row(settings: Settings):
    with closing(connect(settings.db_path, settings.migrations_dir)) as conn:
        return find_sync(conn, TAKE_ID, "camA", "camB")


def _force_audio_lag(monkeypatch: pytest.MonkeyPatch, wrong_s: float) -> None:
    def estimate(dir_a: Path, dir_b: Path):
        result = audio_sync_module.estimate_sync(dir_a, dir_b)
        assert result.status == "ok" and result.offset_s is not None
        return replace(result, offset_s=result.offset_s + wrong_s)

    monkeypatch.setattr(sync_take_module, "estimate_sync", estimate)


@pytest.mark.parametrize(
    ("flashes_a", "wrong_s", "has_row"),
    [
        pytest.param(PAIRS_A, 0.0, True, id="usable_take_has_a_row"),
        pytest.param(PAIRS_A, 1.0, False, id="residual_too_large_has_no_row"),
        pytest.param(FIRST_OF_EACH_PAIR, 1.0, False, id="flash_not_found_has_no_row"),
    ],
)
def test_t_sync_05f_the_database_row_exists_only_for_a_usable_take(
    tmp_path: Path,
    ingest_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    flashes_a: tuple[float, ...],
    wrong_s: float,
    has_row: bool,
):
    """BUG-0065: a reader of the ``sync`` table must never get a mapping that the usability rule refused."""
    make_flash_take(tmp_path / "take", ingest_settings, flashes_a=flashes_a, take_id=TAKE_ID)
    _force_audio_lag(monkeypatch, wrong_s)

    manifest = sync_take(TAKE_ID, settings=ingest_settings)

    assert manifest.status == "ok"
    assert manifest.usable_for_metrics is has_row
    row = _row(ingest_settings)
    assert (row is not None) is has_row, f"row {dict(row) if row else None}, usable {manifest.usable_for_metrics}"
    assert (ingest_settings.data_dir / "takes" / TAKE_ID / "sync.json").is_file()  # sync.json keeps every result


def test_t_sync_05f_a_rerun_that_becomes_unusable_removes_the_old_row(
    tmp_path: Path, ingest_settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    make_flash_take(tmp_path / "take", ingest_settings, take_id=TAKE_ID)
    first = sync_take(TAKE_ID, settings=ingest_settings)
    assert first.usable_for_metrics is True
    assert _row(ingest_settings) is not None

    _force_audio_lag(monkeypatch, 1.0)
    second = sync_take(TAKE_ID, settings=ingest_settings)

    assert second.usable_for_metrics is False
    assert _row(ingest_settings) is None
