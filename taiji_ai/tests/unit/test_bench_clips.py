"""T-BENCH-08 (part): finding the videos by size and SHA-256, the plan file, the clip table (P3.07)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from taiji_ai.bench import BenchError
from taiji_ai.bench.clips import CLIPS, D20_VIDEOS, SEGMENT_S, PlanEntry, VideoSpec, find_videos, read_plan, write_plan


def spec(label: str, data: bytes) -> VideoSpec:
    return VideoSpec(label, len(data), hashlib.sha256(data).hexdigest())


def test_t_bench_08_a_video_is_found_by_size_and_sha_256_whatever_its_name(tmp_path: Path):
    a, b = b"first video bytes", b"second video, longer bytes"
    (tmp_path / "holiday.mp4").write_bytes(a)
    (tmp_path / "x.mov").write_bytes(b)
    (tmp_path / "unrelated.txt").write_bytes(b"something else")

    found = find_videos(tmp_path, {"d20-vA": spec("d20-vA", a), "d20-vB": spec("d20-vB", b)})

    assert found["d20-vA"].name == "holiday.mp4" and found["d20-vB"].name == "x.mov"


def test_t_bench_08_a_file_of_the_right_size_with_another_content_is_not_the_video(tmp_path: Path):
    real = b"abcdefgh"
    (tmp_path / "copy.mp4").write_bytes(b"abcdefgX")  # same size, other bytes
    with pytest.raises(BenchError) as error:
        find_videos(tmp_path, {"d20-vA": spec("d20-vA", real)})
    assert "d20-vA" in str(error.value) and "another SHA-256" in str(error.value)
    assert "copy" not in str(error.value) and str(tmp_path) not in str(error.value)  # labels only


def test_t_bench_08_missing_videos_are_named_by_label_only(tmp_path: Path):
    (tmp_path / "only.mp4").write_bytes(b"one")
    wanted = {"d20-vA": spec("d20-vA", b"one"), "d20-vB": spec("d20-vB", b"two!")}
    with pytest.raises(BenchError, match="d20-vB") as error:
        find_videos(tmp_path, wanted)
    assert "d20-vA" not in str(error.value) and "only" not in str(error.value)


def test_t_bench_08_a_missing_folder_is_refused_without_its_path(tmp_path: Path):
    with pytest.raises(BenchError, match="video folder") as error:
        find_videos(tmp_path / "no_such_folder", {"d20-vA": spec("d20-vA", b"x")})
    assert "no_such_folder" not in str(error.value)


def test_t_bench_08_the_clip_table_is_the_one_of_the_plan():
    assert list(CLIPS) == ["c1", "c2", "c3", "c4", "c5"] and SEGMENT_S == 30.0
    assert [(c.video_label, c.start_s) for c in CLIPS.values()] == [
        ("d20-v2", 300.0), ("d20-v2", 660.0), ("d20-v3", 600.0), ("d20-v1", 500.0), ("d20-v4", 1200.0),
    ]  # fmt: skip
    assert {c.video_label for c in CLIPS.values()} <= set(D20_VIDEOS) and len(D20_VIDEOS) == 4
    for video in D20_VIDEOS.values():
        assert video.label.startswith("d20-v") and len(video.sha256) == 64 and video.size_bytes > 0


def test_t_bench_08_the_plan_is_written_and_read_back(tmp_path: Path):
    entries = [PlanEntry("c1", "rec/a", 300.0, 330.0), PlanEntry("c2", "rec/b", 660.0, 690.0)]
    write_plan(tmp_path / "plan.json", entries)
    assert read_plan(tmp_path / "plan.json") == entries


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        "{}",
        json.dumps([{"clip_id": "c1", "recording_dir": "x", "start_s": 0, "end_s": 1, "extra": 1}]),
        json.dumps([{"clip_id": "c1", "recording_dir": "x", "start_s": 0}]),
        json.dumps([{"clip_id": "c1", "recording_dir": "x", "start_s": 5, "end_s": 5}]),
        json.dumps([{"clip_id": "c1", "recording_dir": "x", "start_s": 0, "end_s": True}]),
        json.dumps([{"clip_id": 1, "recording_dir": "x", "start_s": 0, "end_s": 1}]),
        json.dumps([{"clip_id": "c1", "recording_dir": "x", "start_s": "0", "end_s": 1}]),
        json.dumps([{"clip_id": "c1", "recording_dir": "x", "start_s": 0, "end_s": 1}] * 2),
    ],
    ids=[
        "not json",
        "empty list",
        "object",
        "extra key",
        "missing key",
        "empty range",
        "bool",
        "id type",
        "str",
        "twice",
    ],
)
def test_t_bench_08_a_bad_plan_is_refused(tmp_path: Path, content: str):
    (tmp_path / "plan.json").write_text(content, encoding="utf-8")
    with pytest.raises(BenchError):
        read_plan(tmp_path / "plan.json")


def test_t_bench_08_a_missing_plan_is_refused(tmp_path: Path):
    with pytest.raises(BenchError, match="plan"):
        read_plan(tmp_path / "nothing.json")
