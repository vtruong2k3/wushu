"""T-BENCH-09: numbers derived from a worker's passes, refusals of the orchestrator, report tables (P3.07)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from taiji_ai.bench import BenchError
from taiji_ai.bench.orchestrate import run_benchmark, summarise_worker
from taiji_ai.bench.report import render_tables
from taiji_ai.bench.timing import percentiles


def clip(n_frames: int, span: float, elapsed: list[float], decode: list[float], post: float) -> dict[str, Any]:
    passes = [
        {
            "elapsed_s": e,
            "span_s": span,
            "rtf": e / span,
            "ms_per_frame": 1000.0 * e / n_frames,
            "detect_s": 0.25 * e,
            "estimate_s": 0.125 * e,
            "latency_ms": [10.0 * e, 20.0 * e],
            "window_rtf": [e / span],
        }
        for e in elapsed
    ]
    return {
        "n_frames": n_frames,
        "passes": passes,
        "decode": [{"decode_s": d, "n_frames": n_frames} for d in decode],
        "post": [{"post_s": post}],
        "spread": (max(elapsed) - min(elapsed)) / float(np.median(elapsed)),
        "noisy": False,
        "extra_passes": 0,
        "all_identical": True,
    }


WORKER = {
    "n": 5,
    "repeats": 3,
    "load_s": 3.0,
    "warmup": {"elapsed_s": 6.0},
    "utilisation_before_pct": 15.0,
    "vram": {"measured": False, "reason": "NVML is not installed"},
    "clips": {
        "c1": clip(100, 4.0, [2.0, 4.0, 3.0], [0.4, 0.6], 0.1),
        "c2": clip(50, 2.0, [1.0], [0.2], 0.05),
    },
}


# --- T-BENCH-09a: the derived numbers -------------------------------------------------------------------------------
def test_t_bench_09a_the_medians_sums_and_phases_of_a_worker():
    s = summarise_worker(WORKER)

    c1 = s["per_clip"]["c1"]
    assert (c1["elapsed_median_s"], c1["elapsed_min_s"], c1["elapsed_max_s"]) == (3.0, 2.0, 4.0)
    assert (c1["rtf_median"], c1["rtf_min"], c1["rtf_max"]) == (0.75, 0.5, 1.0)
    assert c1["decode_s_median"] == pytest.approx(0.5) and c1["post_s_median"] == 0.1
    assert c1["end_to_end_s"] == pytest.approx(3.1)  # the run plus what follows it
    assert c1["detect_s_median"] == pytest.approx(0.75) and c1["estimate_s_median"] == pytest.approx(0.375)

    assert s["elapsed_median_s"] == pytest.approx(4.0)  # one pass over both clips: 3.0 + 1.0
    assert s["n_frames"] == 150 and s["span_s"] == 6.0 and s["rtf"] == pytest.approx(4.0 / 6.0)
    assert s["ms_per_frame"] == pytest.approx(1000.0 * 4.0 / 150)
    assert s["rtf_at_30_fps"] == pytest.approx(s["ms_per_frame"] * 30 / 1000.0)
    assert s["rtf_at_60_fps"] == pytest.approx(2.0 * s["rtf_at_30_fps"])
    p = s["phases_s"]
    assert p["decode_s"] == pytest.approx(0.5 + 0.2) and p["detect_s"] == pytest.approx(0.75 + 0.25)
    assert p["other_s"] == pytest.approx(4.0 - p["detect_s"] - p["estimate_s"] - p["decode_s"])
    assert p["post_s"] == pytest.approx(0.15)


def test_t_bench_09a_latency_and_window_percentiles_are_taken_over_all_passes_of_all_clips():
    s = summarise_worker(WORKER)
    series = [10.0 * e for e in (2.0, 4.0, 3.0, 1.0)] + [20.0 * e for e in (2.0, 4.0, 3.0, 1.0)]
    expected = percentiles(series)
    assert s["frame_latency_ms"] == {str(q): v for q, v in expected.items()}
    windows = [2.0 / 4.0, 4.0 / 4.0, 3.0 / 4.0, 1.0 / 2.0]
    assert s["window_rtf"] == {str(q): v for q, v in percentiles(windows, (50, 95)).items()} and s["n_windows"] == 4


def test_t_bench_09a_a_noisy_or_not_identical_clip_is_carried_through():
    worker = copy.deepcopy(WORKER)
    worker["clips"]["c1"]["noisy"] = True
    worker["clips"]["c1"]["all_identical"] = False
    worker["clips"]["c1"]["extra_passes"] = 2
    c1 = summarise_worker(worker)["per_clip"]["c1"]
    assert (c1["noisy"], c1["all_identical"], c1["extra_passes"]) == (True, False, 2)


# --- T-BENCH-09b: refusals before anything runs ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"ns": [5, 10]}, "N = 1"),
        ({"ns": [1, 0]}, "at least 1"),
        ({"repeats": 0}, "repeats"),
        ({"clip_ids": ["c9"]}, "unknown clip"),
        ({"segment_s": 0.0}, "segment"),
    ],
)
def test_t_bench_09b_bad_arguments_are_refused_before_anything_is_read(tmp_path: Path, kwargs: dict, message: str):
    with pytest.raises(BenchError, match=message):
        run_benchmark(tmp_path / "videos", **kwargs)


def test_t_bench_09b_a_folder_without_the_videos_is_refused_with_labels_only(tmp_path: Path):
    (tmp_path / "videos").mkdir()
    with pytest.raises(BenchError, match="d20-v2") as error:
        run_benchmark(tmp_path / "videos", clip_ids=["c1"], work_dir=tmp_path / "work")
    assert str(tmp_path) not in str(error.value)
    assert not (tmp_path / "work").exists()  # nothing was created before the videos were found


# --- T-BENCH-09c: the report tables -------------------------------------------------------------------------------
def fake_result(*, measured_vram: bool) -> dict[str, Any]:
    comparison = {
        "n_frames": 150, "count_agreement": 0.9933, "n_ref_persons": 160, "n_other_persons": 158, "n_pairs": 155,
        "n_missed": 5, "n_extra": 3, "n_uncomparable_ref": 0, "n_uncomparable_other": 1,
        "entry_delay_frames": {"n": 2, "mean": 1.5, "max": 3}, "n_tracks_never_matched": 0,
        "px": {"median": 1.5, "p95": 5.5, "p99": 12.0, "max": 47.0, "n": 4000},
        "norm": {"median": 0.002, "p95": 0.007, "p99": 0.02, "max": 0.06, "n": 4000},
        "group_p95_norm": {"head": 0.004, "trunk": 0.003, "arms": 0.011, "legs": 0.006, "feet": None},
    }  # fmt: skip
    down = {"share_tracked": 0.97, "needs_reselect": False}
    target = {
        "n_frames": 150, "n_both_tracked": 148, "n_ref_only": 2, "n_other_only": 0, "n_uncomparable_frames": 0,
        "px": {"median": 1.2, "p95": 4.4, "p99": 9.9, "max": 30.0, "n": 3800},
        "norm": {"median": 0.0015, "p95": 0.0055, "p99": 0.012, "max": 0.04, "n": 3800},
    }  # fmt: skip
    vram: dict[str, Any] = (
        {
            "measured": True,
            "device": "Fake GPU",
            "driver": "1.0",
            "total_mib": 12288.0,
            "baseline_mib": 1200.0,
            "drift_mib": 350.0,
            "peaks_mib": {"load": 1500.0, "warmup": 3000.0, "measured": 3100.0},
            "peak_total_mib": 3100.0,
            "peak_delta_mib": 1900.0,
            "n_samples": 100,
        }  # fmt: skip
        if measured_vram
        else {"measured": False, "reason": "NVML is not installed"}
    )
    runs = {}
    for n, factor in ((1, 2.0), (5, 1.0)):
        worker = copy.deepcopy(WORKER)
        for c in worker["clips"].values():
            for p in c["passes"]:
                p["elapsed_s"] *= factor / 2.0
        worker.update(n=n, vram=vram)
        runs[str(n)] = {"worker": worker, "summary": summarise_worker(worker)}
    return {
        "ns": [1, 5],
        "environment": {
            "date": "2026-11-16",
            "gpu": "Fake GPU" if measured_vram else None,
            "driver": "1.0" if measured_vram else None,
            "gpu_total_mib": 12288.0 if measured_vram else None,
            "onnxruntime_gpu": "1.32.0",
            "rtmlib": "0.0.16",
            "av": "19.0.2",
            "numpy": "2.5.4",
            "python": "3.12.10",
            "providers": {"det": "CUDAExecutionProvider", "pose": "CUDAExecutionProvider"},
            "utilisation_before_pct": {"1": 15.0, "5": 16.0},
        },  # fmt: skip
        "clips": {
            cid: {
                "video": "d20-v2",
                "start_s": 300.0,
                "n_frames": c["n_frames"],
                "codec": "h264",
                "nominal_fps": 24.0,
                "width": 1920,
                "height": 1080,
                "persons_per_frame": {"0": 0.0, "1": 0.9, "2": 0.1, "3": 0.0, "4+": 0.0},
            }  # fmt: skip
            for cid, c in WORKER["clips"].items()
        },
        "runs": runs,
        "reference": {"c1": down, "c2": down},
        "effect": {
            "5": {
                "pooled": comparison,
                "target_pooled": target,
                "per_clip": {
                    cid: {"comparison": comparison, "downstream": down, "same_target": True, "target": target}
                    for cid in ("c1", "c2")
                },
                "tracked_loss_points": 0.1,
                "new_needs_reselect": 0,
            }
        },
        "rule": {
            "min_count_agreement": 0.99,
            "max_p95_norm": 0.01,
            "max_p99_norm": 0.03,
            "max_tracked_loss_points": 0.5,
            "min_speed_gain": 0.15,
        },  # fmt: skip
        "recommendation": {
            "n": 5,
            "acceptable": {"5": True},
            "reasons": {"5": []},
            "speed_gain_vs_previous": {"5": 0.5},
        },
    }


def test_t_bench_09c_the_tables_hold_the_numbers_of_the_result():
    text = render_tables(fake_result(measured_vram=True))
    for expected in (
        "### Machine and software", "Fake GPU, 12288 MiB", "### Clips", "d20-v2", "### Real-time factor",
        "0.750 (0.500 to 1.000)",  # clip c1 at N = 1: factor 2.0 / 2.0 = 1.0 times the passes
        "### Where the time goes", "### Per-frame latency", "### GPU memory", "1900 (uncertain)",
        "### Cold start", "### Effect of N against N = 1: persons", "99.33 %", "### p95 distance per joint group",
        "n/a",  # the feet group has no distance
        "Supplementary: the target track that P4 receives", "| N = 5 | 150 | 148 | 2 | 0 | 0 | 1.20 |",
        "The rule written before the measurement", "**Recommended N: 5**", "all criteria met",
    ):  # fmt: skip
        assert expected in text, expected


def test_t_bench_09c_a_vram_that_was_not_measured_is_n_a_with_the_reason_never_a_number():
    text = render_tables(fake_result(measured_vram=False))
    assert "not measured" in text and "NVML is not installed" in text
    assert "1900" not in text and "Fake GPU" not in text


def test_t_bench_09c_the_effect_tables_are_left_out_when_only_n_1_was_measured():
    result = fake_result(measured_vram=True)
    result["ns"] = [1]
    result["runs"] = {"1": result["runs"]["1"]}
    result["effect"], result["recommendation"] = (
        {},
        {"n": 1, "acceptable": {}, "reasons": {}, "speed_gain_vs_previous": {}},
    )
    text = render_tables(result)
    assert "Effect of N" not in text and "only N = 1" in text and "**Recommended N: 1**" in text


# --- T-BENCH-09d: the throwaway folder is removed even with read-only files (the ingest makes the source read-only) ---
def test_t_bench_09d_the_throwaway_folder_goes_away_with_its_read_only_files(tmp_path: Path):
    import os
    import stat

    from taiji_ai.bench.orchestrate import _remove_tree

    folder = tmp_path / "bench" / "data" / "recordings" / "abc"
    folder.mkdir(parents=True)
    source = folder / "source.mp4"
    source.write_bytes(b"video bytes")
    os.chmod(source, stat.S_IREAD)  # as ingest_recording leaves the stored source

    _remove_tree(tmp_path / "bench")

    assert not (tmp_path / "bench").exists()


# --- T-BENCH-09e: an ingest that fails is a BenchError that names the label only --------------------------------------
def test_t_bench_09e_a_video_that_cannot_be_ingested_is_a_bench_error_with_its_label(tmp_path: Path):
    from taiji_ai.bench.orchestrate import ingest_throwaway

    garbage = tmp_path / "private_name.mp4"
    garbage.write_bytes(b"this is not a video")

    with pytest.raises(BenchError, match="d20-v9") as error:
        ingest_throwaway({"d20-v9": garbage}, tmp_path / "work")

    assert "private_name" not in str(error.value)
