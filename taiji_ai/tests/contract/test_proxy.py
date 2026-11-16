"""T-IO-10, 10b, 10c, 11, 11b, 23..27: browser proxy H.264 720p (P2.03).

A proxy is created in ``data/recordings/<recording_id>/`` as ``proxy.mp4`` and ``proxy.json`` (``proxy/1``).
Its frames must keep the source timestamps (|delta t| <= 1 frame at 10 points) so that user interactions
on the browser video player match pipeline measurements. The tests of BUG-0052 (a trimmed clip) are in
``test_trimmed_clip.py``.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import av
import numpy as np
import pyarrow.parquet as pq
import pytest

from helpers.media import tamper_pts
from taiji_ai.config import Settings
from taiji_ai.io import ingest as ingest_module
from taiji_ai.io import proxy as proxy_module
from taiji_ai.io.frames import PtsScan, scan_pts_ticks
from taiji_ai.io.ingest import ingest_recording
from taiji_ai.io.probe import probe_video
from taiji_ai.io.proxy import PROXY_ARGS_TEMPLATE, ProxyError, _check_timestamps, make_proxy
from taiji_ai.schemas._base import read_manifest
from taiji_ai.schemas.recording import ProxyManifest, RecordingManifest
from taiji_ai.store.artifacts import sha256_file


def _meta(take_num: int = 1, camera_id: str = "camA") -> dict:
    return {
        "participant_id": "P03",
        "session_id": "S01",
        "take_id": f"S01-P03-T{take_num:02d}",
        "camera_id": camera_id,
    }


def _ingest(video_path: Path, settings: Settings, *, take_num: int = 1, camera_id: str = "camA") -> Path:
    result = ingest_recording(video_path, _meta(take_num, camera_id), settings)
    return settings.data_dir / "recordings" / result.manifest.recording_id


def _ffprobe(path: Path, *args: str) -> str:
    res = subprocess.run(["ffprobe", "-v", "error", *args, "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    assert res.returncode == 0, "ffprobe failed on a proxy file"
    return res.stdout.strip()


class _FakeFfmpeg:
    """Stand-in for ``subprocess.run`` in ``proxy.py``: the ``-version`` call is real, the encoding call is faked."""

    def __init__(
        self, monkeypatch, *, returncode: int = 1, raises: BaseException | None = None, write_tmp: bool = False
    ):
        real_run = subprocess.run
        self.calls: list[list[str]] = []

        def fake(cmd, *args, **kwargs):
            if "-version" in cmd:
                return real_run(cmd, *args, **kwargs)
            self.calls.append(list(cmd))
            if raises is not None:
                raise raises
            if write_tmp:
                Path(cmd[-1]).write_bytes(b"partial")
            return subprocess.CompletedProcess(cmd, returncode, "", "boom: /secret/folder/clip.mp4")

        monkeypatch.setattr(proxy_module.subprocess, "run", fake)


def _no_leftovers(rec_dir: Path) -> None:
    assert not list(rec_dir.glob("proxy.tmp*")), "a temporary proxy file was left behind"


def test_t_io_10_cfr_and_vfr_proxies_keep_timestamps(cfr_video: Path, vfr_video: Path, ingest_settings: Settings):
    for idx, (vid, cam) in enumerate([(cfr_video, "camA"), (vfr_video, "camB")], start=1):
        rec_dir = _ingest(vid, ingest_settings, take_num=idx, camera_id=cam)
        manifest = make_proxy(rec_dir)

        assert isinstance(manifest, ProxyManifest)
        assert manifest.schema_version == "proxy/1"
        assert manifest.n_frames_proxy == manifest.n_frames_source
        assert manifest.check.passed is True
        assert manifest.check.points == min(10, manifest.n_frames_source)
        assert manifest.check.max_abs_dt_frames <= 1.0

        proxy_file = rec_dir / "proxy.mp4"
        assert proxy_file.exists()
        _no_leftovers(rec_dir)

        # Check round-trip through disk
        disk_manifest = read_manifest(rec_dir / "proxy.json", ProxyManifest)
        assert disk_manifest == manifest


def test_t_io_10b_non_zero_start_offset_keeps_relative_timeline(offset_video: Path, ingest_settings: Settings):
    rec_dir = _ingest(offset_video, ingest_settings, take_num=3, camera_id="camA")
    manifest = make_proxy(rec_dir)

    assert manifest.check.passed is True
    assert manifest.check.max_abs_dt_frames <= 1.0

    # Ensure proxy video itself starts cleanly (presentation timestamps start at 0)
    meta = probe_video(rec_dir / "proxy.mp4")
    assert abs(meta.start_time_s) < 0.1


def test_t_io_10c_scale_down_and_no_enlargement(hd_video_1080p: Path, sd_video_480p: Path, ingest_settings: Settings):
    # 1080p -> scaled down to height 720
    rec_hd = _ingest(hd_video_1080p, ingest_settings, take_num=4, camera_id="camA")
    m_hd = make_proxy(rec_hd)
    meta_hd = probe_video(rec_hd / "proxy.mp4")
    assert meta_hd.height == 720
    assert meta_hd.width == 1280
    assert meta_hd.width % 2 == 0
    assert m_hd.height == 720

    # 480p -> not enlarged, stays 480 lines
    rec_sd = _ingest(sd_video_480p, ingest_settings, take_num=5, camera_id="camA")
    m_sd = make_proxy(rec_sd)
    meta_sd = probe_video(rec_sd / "proxy.mp4")
    assert meta_sd.height == 480
    assert meta_sd.width == 640
    assert meta_sd.width % 2 == 0
    assert m_sd.height == 480


def test_t_io_11_rotated_video_produces_upright_proxy(
    rotated_video: Path, ingest_settings: Settings, ffmpeg_first_frame
):
    rec_dir = _ingest(rotated_video, ingest_settings, take_num=6, camera_id="camA")
    manifest = make_proxy(rec_dir)

    assert manifest.rotation_applied == 90
    assert manifest.check.passed is True

    proxy_meta = probe_video(rec_dir / "proxy.mp4")
    assert proxy_meta.rotation == 0  # proxy is upright, container rotation 0

    # Visual check: decoded first frame matches ffmpeg autorotation
    src_frame = ffmpeg_first_frame(rec_dir / "source.mp4")
    proxy_frame = ffmpeg_first_frame(rec_dir / "proxy.mp4")
    # Both are upright; proxy is height-scaled if source > 720, here cfr_video was 320x240 rotated to 240x320
    assert proxy_frame.shape[0] == src_frame.shape[0]
    assert proxy_frame.shape[1] == src_frame.shape[1]
    # L1 pixel difference within compression noise
    diff = np.mean(np.abs(proxy_frame.astype(float) - src_frame.astype(float)))
    assert diff < 15.0


def test_t_io_11b_metadata_is_stripped(tagged_video: Path, ingest_settings: Settings):
    rec_dir = _ingest(tagged_video, ingest_settings, take_num=7, camera_id="camA")
    make_proxy(rec_dir)

    # Inspect format tags with ffprobe CLI
    res = subprocess.run(
        ["ffprobe", "-show_format", "-of", "json", str(rec_dir / "proxy.mp4")],
        capture_output=True,
        text=True,
        check=True,
    )
    tags = json.loads(res.stdout).get("format", {}).get("tags", {})
    assert "location" not in tags
    assert "comment" not in tags


def test_t_io_10_one_frame_video_proxy(one_frame_video: Path, ingest_settings: Settings):
    rec_dir = _ingest(one_frame_video, ingest_settings, take_num=8, camera_id="camA")
    manifest = make_proxy(rec_dir)
    assert manifest.n_frames_proxy == 1
    assert manifest.check.points == 1
    assert manifest.check.passed is True
    assert manifest.check.max_abs_dt_frames <= 1.0


def test_t_io_10_missing_source_or_pts_raises_proxy_error(tmp_path: Path, cfr_video: Path, ingest_settings: Settings):
    rec_dir = _ingest(cfr_video, ingest_settings, take_num=9, camera_id="camA")

    # 1. Non-existent folder
    with pytest.raises(ProxyError, match="does not exist"):
        make_proxy(tmp_path / "absent")

    # 2. Corrupt/missing pts.parquet
    pts_file = rec_dir / "pts.parquet"
    pts_backup = pts_file.read_bytes()
    pts_file.write_bytes(b"garbage")
    with pytest.raises(ProxyError, match="pts.parquet"):
        make_proxy(rec_dir)
    pts_file.unlink()
    with pytest.raises(ProxyError, match="pts.parquet is missing"):
        make_proxy(rec_dir)
    pts_file.write_bytes(pts_backup)

    # 3. Missing source
    src_file = rec_dir / "source.mp4"
    src_backup = src_file.read_bytes()
    os.chmod(src_file, stat.S_IWRITE)
    src_file.unlink()
    with pytest.raises(ProxyError, match="source video is missing"):
        make_proxy(rec_dir)
    src_file.write_bytes(src_backup)

    # 4. Missing recording.json
    rec_json = rec_dir / "recording.json"
    rec_json_backup = rec_json.read_bytes()
    rec_json.unlink()
    with pytest.raises(ProxyError, match="manifest is missing"):
        make_proxy(rec_dir)
    rec_json.write_bytes(rec_json_backup)


def test_t_io_10_check_timestamps_detects_drift_and_mismatches(cfr_video: Path):
    # With equal source timeline
    src_t = np.arange(60) * (1 / 30.0)
    n_proxy, check = _check_timestamps(cfr_video, src_t, 1 / 30.0)
    assert n_proxy == 60 and check.passed is True

    # With drifted timeline (> 1 frame difference)
    drifted_src = src_t + 0.1  # 100 ms drift > 33.3 ms
    _, check_drift = _check_timestamps(cfr_video, drifted_src, 1 / 30.0)
    assert check_drift.passed is False
    assert check_drift.max_abs_dt_frames > 1.0

    # With mismatched frame count: the deviation is measured over the frames both have; the check fails
    short_src = src_t[:30]
    _, check_count = _check_timestamps(cfr_video, short_src, 1 / 30.0)
    assert check_count.passed is False


def test_t_io_23_the_proxy_is_ready_for_a_browser(cfr_video: Path, yuv444_video: Path, ingest_settings: Settings):
    rec_dir = _ingest(cfr_video, ingest_settings, take_num=1)  # cfr_video has an audio track and 60 frames
    make_proxy(rec_dir)
    proxy_file = rec_dir / "proxy.mp4"

    data = proxy_file.read_bytes()
    assert 0 <= data.find(b"moov") < data.find(b"mdat"), "+faststart: the index must come before the media data"
    assert _ffprobe(proxy_file, "-select_streams", "a", "-show_entries", "stream=codec_type") == "", "audio kept"

    with av.open(str(proxy_file)) as container:
        stream = container.streams.video[0]
        packets = sorted((p for p in container.demux(stream) if p.pts is not None and p.size > 0), key=lambda p: p.pts)
    key_index = [i for i, p in enumerate(packets) if p.is_keyframe]
    assert key_index[0] == 0
    assert max(np.diff([*key_index, len(packets)])) <= 30, "-g 30: a keyframe at least every 30 frames"

    rec_444 = _ingest(yuv444_video, ingest_settings, take_num=2)
    assert _ffprobe(yuv444_video, "-select_streams", "v:0", "-show_entries", "stream=pix_fmt") == "yuv444p"
    make_proxy(rec_444)
    assert _ffprobe(rec_444 / "proxy.mp4", "-select_streams", "v:0", "-show_entries", "stream=pix_fmt") == "yuv420p"


def test_t_io_24_proxy_json_describes_what_happened(cfr_video: Path, ingest_settings: Settings, monkeypatch):
    rec_dir = _ingest(cfr_video, ingest_settings)
    seen: list[list[str]] = []
    real_run = subprocess.run

    def spy(cmd, *args, **kwargs):
        seen.append(list(cmd))
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(proxy_module.subprocess, "run", spy)
    manifest = make_proxy(rec_dir)

    [encode] = [c for c in seen if "-i" in c]
    assert encode[1:5] == ["-hide_banner", "-loglevel", "error", "-y"]
    rebuilt = tuple(
        "{source}" if Path(a).name == "source.mp4" else "{proxy}" if Path(a).name.startswith("proxy.tmp-") else a
        for a in encode[5:]
    )
    assert rebuilt == manifest.args, "proxy.json must record the command that really ran"

    def option(flag: str) -> str:
        return PROXY_ARGS_TEMPLATE[PROXY_ARGS_TEMPLATE.index(flag) + 1]

    assert option("-crf") == "23" and option("-g") == "30" and option("-fps_mode") == "passthrough"
    assert option("-pix_fmt") == "yuv420p" and option("-movflags") == "+faststart" and option("-map_metadata") == "-1"
    assert "-an" in PROXY_ARGS_TEMPLATE

    source = read_manifest(rec_dir / "recording.json", RecordingManifest)
    assert manifest.source_sha256 == source.sha256
    assert manifest.proxy_sha256 == sha256_file(rec_dir / "proxy.mp4")
    assert manifest.n_frames_source == pq.read_table(rec_dir / "pts.parquet").num_rows
    assert manifest.n_frames_proxy == scan_pts_ticks(rec_dir / "proxy.mp4").pts.size
    assert manifest.height == probe_video(rec_dir / "proxy.mp4").height
    version_line = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    assert manifest.ffmpeg == version_line.split()[2]


@pytest.mark.parametrize(
    ("fake", "message"),
    [
        ({"returncode": 1, "write_tmp": True}, "ffmpeg failed"),
        ({"raises": subprocess.TimeoutExpired("ffmpeg", 1)}, "timed out"),
    ],
    ids=["non-zero exit", "timeout"],
)
def test_t_io_25_an_ffmpeg_failure_leaves_nothing_and_keeps_the_old_pair(
    cfr_video: Path, ingest_settings: Settings, monkeypatch, fake: dict, message: str
):
    rec_dir = _ingest(cfr_video, ingest_settings)
    make_proxy(rec_dir)
    before = ((rec_dir / "proxy.mp4").read_bytes(), (rec_dir / "proxy.json").read_bytes())

    _FakeFfmpeg(monkeypatch, **fake)
    with pytest.raises(ProxyError, match=message) as exc:
        make_proxy(rec_dir)

    assert "secret" not in str(exc.value) and "clip.mp4" not in str(exc.value), "the ffmpeg text can hold a path"
    assert ((rec_dir / "proxy.mp4").read_bytes(), (rec_dir / "proxy.json").read_bytes()) == before
    _no_leftovers(rec_dir)


def test_t_io_25_a_failure_on_the_first_proxy_leaves_no_files(cfr_video: Path, ingest_settings: Settings, monkeypatch):
    rec_dir = _ingest(cfr_video, ingest_settings)
    _FakeFfmpeg(monkeypatch, returncode=1, write_tmp=True)
    with pytest.raises(ProxyError, match="ffmpeg failed"):
        make_proxy(rec_dir)
    assert not (rec_dir / "proxy.mp4").exists() and not (rec_dir / "proxy.json").exists()
    _no_leftovers(rec_dir)


@pytest.mark.parametrize("failure", ["garbled output", "cannot run"])
def test_t_io_25_an_unreadable_ffmpeg_version_is_an_error_and_is_not_remembered(
    cfr_video: Path, ingest_settings: Settings, monkeypatch, failure: str
):
    rec_dir = _ingest(cfr_video, ingest_settings)
    real_run = subprocess.run

    def broken(cmd, *args, **kwargs):
        if "-version" not in cmd:
            return real_run(cmd, *args, **kwargs)
        if failure == "cannot run":
            raise OSError("no such program")
        return subprocess.CompletedProcess(cmd, 0, "this is not what ffmpeg prints\n", "")

    proxy_module._ffmpeg_version.cache_clear()
    try:
        monkeypatch.setattr(proxy_module.subprocess, "run", broken)
        with pytest.raises(ProxyError, match="ffmpeg version"):
            make_proxy(rec_dir)
        assert not (rec_dir / "proxy.mp4").exists()  # it fails before the encoding, not after

        monkeypatch.undo()  # ffmpeg is fine again: the failure must not have been cached as "unknown"
        assert make_proxy(rec_dir).ffmpeg != "unknown"
    finally:
        proxy_module._ffmpeg_version.cache_clear()


def test_t_io_25_a_missing_ffmpeg_is_reported(cfr_video: Path, ingest_settings: Settings, monkeypatch):
    rec_dir = _ingest(cfr_video, ingest_settings)
    real_which = shutil.which
    monkeypatch.setattr(
        proxy_module.shutil, "which", lambda name, *a, **k: None if name == "ffmpeg" else real_which(name, *a, **k)
    )
    with pytest.raises(ProxyError, match="not available"):
        make_proxy(rec_dir)
    assert not (rec_dir / "proxy.mp4").exists()


def test_t_io_25_a_failed_manifest_write_leaves_no_stale_manifest(
    cfr_video: Path, ingest_settings: Settings, monkeypatch
):
    rec_dir = _ingest(cfr_video, ingest_settings)
    make_proxy(rec_dir)
    assert (rec_dir / "proxy.json").exists()

    def disk_full(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(proxy_module, "write_manifest", disk_full)
    with pytest.raises(ProxyError):
        make_proxy(rec_dir)
    # The new proxy.mp4 is in place, so the old proxy.json (the hash of the old file) would be a lie:
    # a missing manifest means "not usable".
    assert not (rec_dir / "proxy.json").exists()
    _no_leftovers(rec_dir)


def test_t_io_26_a_failed_check_keeps_and_marks_the_proxy(cfr_video: Path, ingest_settings: Settings):
    rec_dir = _ingest(cfr_video, ingest_settings)
    tamper_pts(rec_dir, shift_s=0.2)  # 6 frames at 30 fps

    manifest = make_proxy(rec_dir)

    assert manifest.check.passed is False
    assert manifest.check.max_abs_dt_frames == pytest.approx(6.0, abs=0.01)
    assert (rec_dir / "proxy.mp4").is_file() and (rec_dir / "proxy.json").is_file()
    assert read_manifest(rec_dir / "proxy.json", ProxyManifest) == manifest


def test_t_io_26_a_frame_count_mismatch_is_marked_with_the_true_counts(cfr_video: Path, ingest_settings: Settings):
    rec_dir = _ingest(cfr_video, ingest_settings)
    tamper_pts(rec_dir, drop_last=5)

    manifest = make_proxy(rec_dir)

    assert manifest.check.passed is False
    assert (manifest.n_frames_source, manifest.n_frames_proxy) == (55, 60)
    assert (rec_dir / "proxy.mp4").is_file() and (rec_dir / "proxy.json").is_file()


def test_t_io_26_what_cannot_be_measured_is_an_error_not_a_made_up_number(
    cfr_video: Path, one_frame_video: Path, monkeypatch
):
    with pytest.raises(ProxyError, match="no frames"):  # no source frame
        _check_timestamps(cfr_video, np.array([]), 1 / 30.0)
    with pytest.raises(ProxyError, match="interval"):  # one source frame at 0.5 s, no interval to express it in frames
        _check_timestamps(one_frame_video, np.array([0.5]), None)
    n_proxy, check = _check_timestamps(one_frame_video, np.array([0.0]), None)  # a real zero deviation
    assert n_proxy == 1 and check.passed is True and check.max_abs_dt_frames == 0.0

    empty = PtsScan(np.array([], dtype=np.int64), scan_pts_ticks(cfr_video).time_base, 0)
    monkeypatch.setattr(proxy_module, "scan_pts_ticks", lambda path: empty)
    with pytest.raises(ProxyError, match="no frames"):  # no proxy frame
        _check_timestamps(cfr_video, np.arange(3) / 30.0, 1 / 30.0)


def test_t_io_27_ingest_with_proxy_on_an_already_ingested_file(cfr_video: Path, ingest_settings: Settings):
    first = ingest_recording(cfr_video, _meta(), ingest_settings)
    assert first.created and first.proxy is None and first.proxy_error is None

    second = ingest_recording(cfr_video, _meta(), ingest_settings, proxy=True)

    rec_dir = ingest_settings.data_dir / "recordings" / first.manifest.recording_id
    assert second.created is False
    assert second.proxy is not None and second.proxy.check.passed is True
    assert (rec_dir / "proxy.mp4").is_file() and (rec_dir / "proxy.json").is_file()


def test_t_io_27_a_proxy_failure_after_ingest_keeps_the_recording(
    cfr_video: Path, ingest_settings: Settings, monkeypatch
):
    def boom(_rec_dir):
        raise ProxyError("boom")

    monkeypatch.setattr(ingest_module, "make_proxy", boom)

    result = ingest_recording(cfr_video, _meta(), ingest_settings, proxy=True)

    assert result.created is True and result.proxy is None and result.proxy_error == "boom"
    assert (ingest_settings.data_dir / "recordings" / result.manifest.recording_id / "recording.json").is_file()

    # the same file: the proxy step fails again
    again = ingest_recording(cfr_video, _meta(), ingest_settings, proxy=True)
    assert again.created is False and again.proxy is None and again.proxy_error == "boom"
