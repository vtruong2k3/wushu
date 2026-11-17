"""T-DET-10: the numbers and tables of the detector comparison (P3.09), on made-up detections: no model, no video."""

from __future__ import annotations

import numpy as np
import pytest

from taiji_ai.bench.detector_compare import (
    above,
    iou_profile,
    pick_sample,
    recall_by_limit,
    render_tables,
    speed_summary,
    summarise_c,
    summarise_r,
)

REF = (100.0, 100.0, 200.0, 400.0)
H = 1000.0


def det(*boxes: tuple[float, float, float, float], score: float = 0.9) -> np.ndarray:
    return np.array([(*b, score) for b in boxes], np.float32).reshape(-1, 5)


def entry(i: int, reference=REF, negative: bool = False) -> dict:
    return {"id": f"fc-{i:03d}", "reference": reference, "negative": negative, "image_height": H}


# --- set R ----------------------------------------------------------------------------------------------------------
def test_t_det_10_recall_pairs_missed_ids_negatives_and_frames_without_a_reference():
    entries = [
        entry(1),
        entry(2),
        entry(3),
        entry(4),
        entry(5, negative=True, reference=None),
        entry(6, reference=None),
    ]
    hit, off = det(REF), det((600, 100, 700, 400))
    a = [hit, off, hit, off, det((50, 50, 400, 900)), hit]  # A misses 2 and 4; a performer-sized box on the negative
    b = [hit, hit, off, off, det(), hit]  # B misses 3 and 4
    r = summarise_r(entries, a, b)
    assert r["n_positive"] == 4 and r["no_reference"] == 1  # fc-006 has no reference and is not a negative
    assert (r["paired"]["both"], r["paired"]["only_a"], r["paired"]["only_b"], r["paired"]["neither"]) == (1, 1, 1, 1)
    assert r["paired"]["recall_a"] == 0.5 and r["paired"]["recall_b"] == 0.5
    assert r["mcnemar_p"] == 1.0
    assert r["negatives"] == {"n": 1, "false_alarms_a": 1, "false_alarms_b": 0}
    assert r["missed_ids_a"] == ["fc-002", "fc-004"] and r["missed_ids_b"] == ["fc-003", "fc-004"]


def test_t_det_10_a_small_box_on_a_negative_frame_is_not_a_false_alarm():
    r = summarise_r(
        [entry(1, negative=True, reference=None)], [det((0, 0, 50, 100))], [det()]
    )  # 100 px of 1000: a person far away
    assert r["negatives"]["false_alarms_a"] == 0


def test_t_det_10_the_score_limit_is_strict_and_applies_to_the_stored_scores():
    entries = [entry(1), entry(2)]
    a = [det(REF, score=0.6), det(REF, score=0.31)]
    b = [det(REF, score=0.95), det(REF, score=0.5)]
    assert above(det(REF, score=0.3), 0.3).shape == (0, 5)  # equal is dropped
    by = {x["limit"]: x for x in recall_by_limit(entries, a, b, limits=(0.3, 0.5, 0.7))}
    assert (by[0.3]["recall_a"], by[0.3]["recall_b"]) == (1.0, 1.0)
    # A keeps its 0.6 only; B keeps its 0.95 (its 0.5 is not above the limit 0.5)
    assert (by[0.5]["recall_a"], by[0.5]["recall_b"]) == (0.5, 0.5)
    assert (by[0.7]["recall_a"], by[0.7]["recall_b"]) == (0.0, 0.5)


def test_t_det_10_no_positive_frame_gives_n_a_not_zero_and_unequal_lengths_are_refused():
    r = summarise_r([entry(1, negative=True, reference=None)], [det()], [det()])
    assert r["n_positive"] == 0 and r["paired"]["recall_a"] is None
    with pytest.raises(ValueError, match="same length"):
        summarise_r([entry(1)], [det()], [])


# --- set C ----------------------------------------------------------------------------------------------------------
def clip_of(has_a: list[bool], has_b: list[bool], fps: float = 10.0) -> dict:
    box = (100.0, 100.0, 300.0, 700.0)  # 600 px of 1000: a performer-sized box
    n = len(has_a)
    return {
        "t_sec": np.arange(n) / fps,
        "dets_a": [det(box) if h else det() for h in has_a],
        "dets_b": [det(box) if h else det() for h in has_b],
        "image_height": H,
    }


def test_t_det_10_clips_agreement_runs_and_dropouts_in_seconds():
    a = [True, True, True, False, False, True, True, True, True, True]
    b = [True, True, True, True, True, True, True, True, False, True]
    c = summarise_c({"c1": clip_of(a, b)})
    assert c["totals"] == {"frames": 10, "both": 7, "only_a": 1, "only_b": 2, "neither": 0}
    assert c["runs_only_a"] == 1 and c["runs_only_b"] == 1
    run_b = next(r for r in c["runs"] if r["direction"] == "only_b")
    assert (run_b["start_index"], run_b["end_index"], run_b["frames"]) == (3, 4, 2)
    assert run_b["seconds"] == pytest.approx(0.2) and run_b["t_sec"] == pytest.approx(
        0.3
    )  # the first of the two middle frames
    assert c["dropouts"]["a_loses_what_b_has"] == {
        "count": 1,
        "total_s": pytest.approx(0.2),
        "longest_s": pytest.approx(0.2),
        "over_half_second": 0,
    }
    assert c["dropouts"]["b_loses_what_a_has"]["count"] == 1


def test_t_det_10_the_same_frames_at_a_slower_rate_give_longer_dropouts_not_more_frames():
    a = [True, False, False, False, False, False, False, True]
    b = [True] * 8
    fast = summarise_c({"c": clip_of(a, b, fps=30.0)})["dropouts"]["a_loses_what_b_has"]
    slow = summarise_c({"c": clip_of(a, b, fps=6.0)})["dropouts"]["a_loses_what_b_has"]
    assert fast["longest_s"] == pytest.approx(6 / 30.0) and slow["longest_s"] == pytest.approx(1.0)
    assert fast["over_half_second"] == 0 and slow["over_half_second"] == 1


def test_t_det_10_stability_is_pooled_without_pairing_across_the_clips():
    c = summarise_c({"c1": clip_of([True] * 5, [True] * 5), "c2": clip_of([True] * 5, [True] * 5)})
    assert c["stability"]["a"]["pairs"] == 8  # 4 + 4: the last frame of c1 is not paired with the first of c2
    assert c["stability"]["a"]["frames"] == 5 + 5 + 3  # the three frames without a box between the clips


def test_t_det_10_no_frame_with_a_box_gives_n_a_stability_and_no_runs():
    c = summarise_c({"c1": clip_of([False] * 4, [False] * 4)})
    assert c["runs"] == [] and c["stability"]["a"]["one_minus_iou"] is None
    assert c["dropouts"]["a_loses_what_b_has"]["longest_s"] is None


def test_t_det_10_clips_must_cover_the_same_frames():
    bad = clip_of([True, True], [True, True])
    bad["dets_b"] = bad["dets_b"][:1]
    with pytest.raises(ValueError, match="same frames"):
        summarise_c({"c1": bad})


def test_t_det_10_the_sample_for_the_review_is_everything_up_to_the_limit_and_then_seeded():
    runs = [{"clip": "c1", "start_index": i * 10, "direction": "only_b"} for i in range(100)]
    few = pick_sample(runs[:5], k=60)
    assert [r["id"] for r in few] == ["dc-001", "dc-002", "dc-003", "dc-004", "dc-005"]
    a, b = pick_sample(runs, k=60, seed=1), pick_sample(runs, k=60, seed=1)
    assert len(a) == 60 and [r["start_index"] for r in a] == [r["start_index"] for r in b]  # deterministic
    assert [r["start_index"] for r in a] == sorted(r["start_index"] for r in a)  # in order, ids follow the order
    assert [r["start_index"] for r in a] != [r["start_index"] for r in pick_sample(runs, k=60, seed=2)]
    assert len({r["id"] for r in a}) == 60


# --- speed and the tables -------------------------------------------------------------------------------------------
def worker_json(scale: float = 1.0) -> dict:
    def rep(p50: float) -> dict:
        return {
            "model_ms": {"p50": p50, "p95": p50 * 1.5, "p99": p50 * 2.0, "mean": p50},
            "end_to_end_ms": {"p50": p50 * 2, "p95": p50 * 3, "p99": p50 * 4, "mean": p50 * 2},
            "pre_ms_median": 1.0,
            "post_ms_median": 0.5,
        }

    return {
        "speed": {"n_frames": 300, "warmup": 30, "repeats": [rep(10 * scale), rep(12 * scale), rep(20 * scale)]},
        "vram": {"measured": True, "peak_delta_mib": 500.0, "baseline_mib": 1200.0},
        "load_s": 2.5,
    }


def test_t_det_10_speed_is_the_median_over_the_repeats_of_each_percentile():
    s = speed_summary(worker_json())
    assert s["model_ms"] == {"p50": 12.0, "p95": 18.0, "p99": 24.0}  # medians: the means would be 14, 21, 28
    assert s["end_to_end_ms"]["p50"] == 24.0 and s["vram_peak_delta_mib"] == 500.0 and s["repeats"] == 3


def test_t_det_10_without_a_speed_section_or_a_vram_reading_the_values_are_none():
    s = speed_summary({"vram": {"measured": False, "reason": "no NVML"}})
    assert s["vram_peak_delta_mib"] is None and "model_ms" not in s


def result_for_tables() -> dict:
    entries = [entry(1), entry(2)]
    r = summarise_r(entries, [det(REF), det()], [det(REF), det(REF)])
    return {
        "speed": {"a": speed_summary(worker_json()), "b": speed_summary(worker_json(0.8))},
        "r": r,
        "r_by_limit": recall_by_limit(entries, [det(REF), det()], [det(REF), det(REF)]),
        "c": summarise_c({"c1": clip_of([True] * 6, [True] * 6)}),
    }


def test_t_det_10_the_tables_hold_the_numbers_and_never_print_n_a_as_zero():
    text = render_tables(result_for_tables())
    for expected in (
        "Speed and memory",
        "12.00",
        "| 500 |",
        "Recall of the performer",
        "50.0 %",
        "100.0 %",
        "McNemar",
        "The clips",
        "Stability",
        "Dropouts",
    ):
        assert expected in text, expected
    empty = {**result_for_tables(), "c": summarise_c({}), "r": summarise_r([], [], []), "r_by_limit": []}
    text = render_tables(empty)
    assert "n/a" in text and "0.0 %" not in text


def test_t_det_10_the_decision_and_the_review_appear_when_they_are_given():
    result = result_for_tables()
    result["review"] = {"n_discordant": 12, "n_reviewed": 12, "b_better": 3, "a_better": 1, "unsure": 2}
    result["decision"] = {
        "outcome": "not_materially_better",
        "criterion": None,
        "reasons": ["R: something", "C: something"],
    }
    text = render_tables(result)
    assert "not_materially_better" in text and "- R: something" in text and "| 12 | 12 | 3 | 1 | 2 |" in text


def test_t_det_10_the_tables_name_no_path_and_no_file():
    text = render_tables(result_for_tables())
    assert ".mp4" not in text and "\\" not in text and ".npz" not in text and ".onnx" not in text


# --- the box agreement apart from the rule --------------------------------------------------------------------------
def test_t_det_10_the_iou_profile_separates_a_loose_box_from_a_missing_one():
    entries = [entry(1), entry(2), entry(3), entry(4, negative=True, reference=None), entry(5, reference=None)]
    tight = det((100, 100, 200, 400))  # IoU 1 with the reference
    loose = det((50, 50, 250, 500))  # 100 x 300 inside 200 x 450: IoU 1/3
    none = det()
    a = [loose, loose, none, none, none]
    b = [tight, loose, tight, none, none]
    p = iou_profile(entries, a, b)
    assert p["n"] == 3  # the negative and the frame without a reference are not in it
    at = {x["iou_min"]: x for x in p["recall_at"]}
    assert (at[0.3]["recall_a"], at[0.3]["recall_b"]) == (
        pytest.approx(2 / 3),
        1.0,
    )  # a loose box is still found at 0.3
    assert (at[0.5]["recall_a"], at[0.5]["recall_b"]) == (0.0, pytest.approx(2 / 3))
    assert p["a"]["p50"] == pytest.approx(1 / 3, abs=0.01) and p["b"]["p50"] == 1.0


def test_t_det_10_the_iou_profile_with_no_positive_frame_is_n_a():
    p = iou_profile([entry(1, negative=True, reference=None)], [det()], [det()])
    assert p["n"] == 0 and p["a"] is None and p["recall_at"][0]["recall_a"] is None


def test_t_det_10_the_iou_table_appears_in_the_tables_when_given():
    result = result_for_tables()
    result["r_iou"] = iou_profile([entry(1)], [det(REF)], [det(REF)])
    text = render_tables(result)
    assert "Box agreement with the reference box" in text and "| 0.5 | 100.0 % | 100.0 % |" in text


def test_t_det_10_the_representative_frame_of_a_run_is_its_middle_one():
    a = [True] * 3 + [False] * 3 + [True] * 4
    b = [True] * 10
    c = summarise_c({"c1": clip_of(a, b)})
    (run,) = c["runs"]
    assert (run["start_index"], run["end_index"], run["frames"]) == (3, 5, 3)
    assert run["t_sec"] == pytest.approx(0.4)  # frame 4 of 3..5


def test_t_det_10_a_box_with_an_iou_of_exactly_the_limit_counts_at_that_limit():
    entries = [entry(1)]  # REF = (100, 100, 200, 400): area 30000
    exactly_half = det((100, 100, 200, 700))  # area 60000, inside: IoU = 0.5
    p = iou_profile(entries, [exactly_half], [exactly_half])
    at = {x["iou_min"]: x for x in p["recall_at"]}
    assert at[0.5]["recall_a"] == 1.0 and at[0.7]["recall_a"] == 0.0
