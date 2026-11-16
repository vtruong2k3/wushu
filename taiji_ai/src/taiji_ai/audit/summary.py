"""The numbers and the tables of the failure review (P3.08), from the final labels.

A row is a **failure** (counted) when its final verdict is ``failure`` with severity ``S1`` or ``S2``; ``S3`` is
minor, listed in the cases and not counted; ``ok`` rows are not failures. What is reported:

* per rule: how many frames the rule took and how many of them are failures (its **precision**); * the **blind
sample**: how many failures among the frames no rule pointed at, with a Wilson 95 % interval (the estimate of how
often the pose fails on this footage, which the rules cannot give because they select the suspect frames); * failures
by type, by view, by situation and by joint group (a failure counts once in every group it names); * the **score**: of
the failures that name joints, how many a mask at ``tau_kp`` would **not** remove (at least one wrong joint with a
score at or above ``tau_kp``), from the scores in the data;
* the failures that depend on the detector cadence (the label ``cadence``);
* every failure case by ID, video label, time and frame index (never a file name or a path).

Two markers in the note of a row say that the frame is not an ordinary pose question; they are conventions of the
review, set by the reviewer, and the numbers keep them apart (nothing is dropped): ``[track]`` (the performer is in the
picture with a good skeleton in the raw pose but the target link was lost: a tracker event, not a pose failure) and
``[edit]`` (a fade, a dissolve or a title overlay of the video editing: not footage of a capture).

The review is a sample chosen to find failures: only the blind sample estimates a rate.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from taiji_ai.audit.labels import (
    FAILURE_TYPES,
    SITUATIONS,
    VIEWS,
    ReviewRow,
    agreement,
    expand_joints,
    final_label,
    score_warns,
)
from taiji_ai.bench.compare import JOINT_GROUPS
from taiji_ai.pose.skeleton import JOINTS

COUNTED = ("S1", "S2")
BANDS = (
    (0.0, 0.3, "under 0.3"),
    (0.3, 0.5, "0.3 to 0.5"),
    (0.5, 0.7, "0.5 to 0.7"),
    (0.7, 0.9, "0.7 to 0.9"),
    (0.9, math.inf, "0.9 or more"),
)
EDIT_MARK = "[edit]"
TRACK_MARK = "[track]"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval of ``k`` successes in ``n`` trials (95 % for ``z = 1.96``); ``None`` for ``n = 0``."""
    if n <= 0:
        return None
    p = k / n
    denominator = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def _groups_of(joints: Sequence[str]) -> set[str]:
    indices = set(expand_joints(joints))
    return {g for g, names in JOINT_GROUPS.items() if indices & {JOINTS.index(n) for n in names}}


def summarise(rows: Sequence[ReviewRow], scores_by_id: Mapping[str, np.ndarray], tau: float) -> dict[str, Any]:
    """All the numbers of the review from the final labels (``scores_by_id[cid]``: the 26 scores at that frame)."""
    labels = {r.cid: final_label(r) for r in rows}
    counted = {cid for cid, label in labels.items() if label.verdict == "failure" and label.severity in COUNTED}

    by_rule: dict[str, dict[str, Any]] = {}
    for r in rows:
        for tag in r.tags:
            entry = by_rule.setdefault(tag, {"n": 0, "failures": 0})
            entry["n"] += 1
            entry["failures"] += int(r.cid in counted)
    for entry in by_rule.values():
        entry["precision"] = entry["failures"] / entry["n"]

    editing = {cid for cid, label in labels.items() if EDIT_MARK in label.note}
    tracking = {cid for cid, label in labels.items() if TRACK_MARK in label.note}
    ordinary = counted - editing - tracking  # the pose failures of ordinary frames

    def blind_stats(blind_rows: Sequence[ReviewRow]) -> dict[str, Any]:
        failures = sum(r.cid in counted for r in blind_rows)
        interval = wilson(failures, len(blind_rows))
        return {
            "n": len(blind_rows),
            "failures": failures,
            "rate": failures / len(blind_rows) if blind_rows else None,
            "wilson95": list(interval) if interval else None,
        }

    blind = [r for r in rows if r.tags == ("blind",)]

    def frames_and_failures(field: str, values: Sequence[str]) -> dict[str, dict[str, int]]:
        out = {v: {"frames": 0, "failures": 0} for v in values}
        for r in rows:
            value = getattr(labels[r.cid], field)
            out[value]["frames"] += 1
            out[value]["failures"] += int(r.cid in counted)
        return out

    by_video: dict[str, dict[str, int]] = {}
    for r in rows:
        entry = by_video.setdefault(r.video, {"frames": 0, "failures": 0, "ordinary_failures": 0})
        entry["frames"] += 1
        entry["failures"] += int(r.cid in counted)
        entry["ordinary_failures"] += int(r.cid in ordinary)

    by_group: Counter[str] = Counter()
    not_warned = warned = with_joints = 0
    ord_not_warned = ord_warned = ord_with_joints = 0
    wrong_max: list[float] = []  # the highest score among the wrong joints of each ordinary failure that names joints
    cadence: Counter[str] = Counter()
    cases = []
    for r in rows:
        label = labels[r.cid]
        if label.verdict != "failure":
            continue
        warns = score_warns(label.joints, scores_by_id[r.cid], tau) if r.cid in scores_by_id else None
        if r.cid in counted:
            by_group.update(_groups_of(label.joints))
            cadence[label.cadence or "missing"] += 1
            if warns is not None:
                with_joints += 1
                not_warned += int(not warns)
                warned += int(warns)
                if r.cid in ordinary:
                    ord_with_joints += 1
                    ord_not_warned += int(not warns)
                    ord_warned += int(warns)
                    wrong = np.asarray(scores_by_id[r.cid], dtype=np.float64)[expand_joints(label.joints)]
                    if np.isfinite(wrong).any():
                        wrong_max.append(float(np.nanmax(wrong)))
        cases.append(
            {
                "id": r.cid, "video": r.video, "t_sec": r.t_sec, "frame_index": r.frame_index, "type": label.type,
                "joints": list(label.joints), "severity": label.severity, "view": label.view,
                "situation": label.situation, "cadence": label.cadence or "missing", "score_warns": warns,
                "counted": r.cid in counted, "tags": list(r.tags),
            }
        )  # fmt: skip
    return {
        "n_rows": len(rows),
        "n_failures": len(counted),
        "n_failures_pose": len(counted - tracking),
        "n_failures_ordinary": len(ordinary),
        "by_video": dict(sorted(by_video.items())),
        "markers": {
            "edit": {"frames": len(editing), "failures": len(editing & counted)},
            "track": {"frames": len(tracking), "failures": len(tracking & counted)},
        },
        "n_minor": sum(1 for lab in labels.values() if lab.verdict == "failure" and lab.severity == "S3"),
        "n_ok": sum(1 for lab in labels.values() if lab.verdict == "ok"),
        "agreement": {k: list(v) for k, v in agreement(rows).items()},
        "by_type": dict(Counter(labels[c].type for c in counted)),
        "by_view": frames_and_failures("view", VIEWS),
        "by_situation": frames_and_failures("situation", SITUATIONS),
        "by_group": {g: by_group.get(g, 0) for g in JOINT_GROUPS},
        "by_rule": by_rule,
        "blind": blind_stats(blind),
        "blind_without_edit": blind_stats([r for r in blind if r.cid not in editing]),
        "score": {
            "tau_kp": tau,
            "failures_with_joints": with_joints,
            "not_warned": not_warned,
            "warned": warned,
            "share_not_warned": not_warned / with_joints if with_joints else None,
        },
        "score_ordinary": {
            "failures_with_joints": ord_with_joints,
            "not_warned": ord_not_warned,
            "warned": ord_warned,
            "share_not_warned": ord_not_warned / ord_with_joints if ord_with_joints else None,
            "wrong_max_bands": {name: sum(lo <= v < hi for v in wrong_max) for lo, hi, name in BANDS},
            "wrong_max_median": float(np.median(wrong_max)) if wrong_max else None,
        },
        "cadence": dict(cadence),
        "cases": cases,
    }


def _f(x: float | None, digits: int = 3) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def _pct(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{100.0 * x:.{digits}f} %"


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    return "\n".join(lines + ["| " + " | ".join(row) + " |" for row in rows])


def render_tables(summary: Mapping[str, Any]) -> str:
    """The tables of the report; a value that does not exist is ``n/a``, never 0."""
    s = summary
    out: list[str] = []

    def section(title: str, body: str) -> None:
        out.append(f"### {title}\n\n{body}\n")

    section(
        "The frames reviewed",
        _table(
            ["Frames", "Failures (S1, S2)", "Minor (S3)", "Ok"],
            [[str(s["n_rows"]), str(s["n_failures"]), str(s["n_minor"]), str(s["n_ok"])]],
        ),
    )
    mk = s["markers"]
    marker_table = _table(
        ["Marker", "Meaning", "Frames", "Failures among them"],
        [
            [
                "[track]",
                "performer in the picture with a good skeleton, target link lost (tracker event)",
                str(mk["track"]["frames"]),
                str(mk["track"]["failures"]),
            ],
            [
                "[edit]",
                "fade, dissolve or title of the video editing (not a capture)",
                str(mk["edit"]["frames"]),
                str(mk["edit"]["failures"]),
            ],
        ],
    )
    section(
        "Frames that are not an ordinary pose question (markers in the notes; nothing is dropped)",
        f"{marker_table}\n\nFailures (S1, S2) without the [track] frames: {s['n_failures_pose']}. Pose failures of "
        f"ordinary frames (neither marker): {s['n_failures_ordinary']}.",
    )
    section(
        "Frames and failures by video (frames reviewed in the sample, not a rate)",
        _table(
            ["Video", "Frames", "Failures (S1, S2)", "Pose failures of ordinary frames"],
            [[v, str(e["frames"]), str(e["failures"]), str(e["ordinary_failures"])] for v, e in s["by_video"].items()]
            or [["n/a", "0", "0", "0"]],
        ),
    )
    ag = s["agreement"]
    section(
        "Agreement of the person with the agent (over the rows the person looked at)",
        _table(
            ["Field", "Rows looked at", "Agree", "Share"],
            [[name, str(n), str(a), _pct(a / n if n else None)] for name, (n, a) in ag.items()],
        ),
    )
    section(
        "Precision of each rule (failures among the frames the rule took)",
        _table(
            ["Rule", "Frames", "Failures", "Precision"],
            [[name, str(e["n"]), str(e["failures"]), _pct(e["precision"])] for name, e in sorted(s["by_rule"].items())],
        ),
    )

    def blind_row(name: str, b: Mapping[str, Any]) -> list[str]:
        interval = "n/a" if b["wilson95"] is None else f"{_pct(b['wilson95'][0])} to {_pct(b['wilson95'][1])}"
        return [name, str(b["n"]), str(b["failures"]), _pct(b["rate"]), interval]

    section(
        "The blind sample (frames no rule pointed at): the only estimate of how often the pose fails",
        _table(
            ["Sample", "Frames", "Failures", "Rate", "Wilson 95 % interval"],
            [blind_row("all blind frames", s["blind"]), blind_row("without [edit] frames", s["blind_without_edit"])],
        ),
    )
    section(
        "Failures by type",
        _table(["Type", "Failures"], [[t, str(s["by_type"].get(t, 0))] for t in FAILURE_TYPES]),
    )
    for title, key in (("Failures by view", "by_view"), ("Failures by situation", "by_situation")):
        section(
            title + " (frames reviewed in the sample, not a rate)",
            _table(
                ["Value", "Frames", "Failures"], [[v, str(e["frames"]), str(e["failures"])] for v, e in s[key].items()]
            ),
        )
    section(
        "Failures by joint group (a failure counts in every group it names)",
        _table(["Group", "Failures"], [[g, str(n)] for g, n in s["by_group"].items()]),
    )
    sc, so = s["score"], s["score_ordinary"]
    section(
        f"Does the score warn? (a mask at tau_kp = {sc['tau_kp']} would remove every wrong joint)",
        _table(
            ["Failures", "That name joints", "Removed by the mask", "Kept by the mask", "Share kept"],
            [
                [
                    "all failures",
                    str(sc["failures_with_joints"]),
                    str(sc["warned"]),
                    str(sc["not_warned"]),
                    _pct(sc["share_not_warned"]),
                ],
                [
                    "ordinary frames only",
                    str(so["failures_with_joints"]),
                    str(so["warned"]),
                    str(so["not_warned"]),
                    _pct(so["share_not_warned"]),
                ],
            ],
        ),
    )
    bands = so["wrong_max_bands"]
    section(
        "How high is the score of the wrong joints? (ordinary failures that name joints)",
        _table(
            ["Highest score of a wrong joint", "Failures"],
            [[name, str(n)] for name, n in bands.items()] + [["median", _f(so["wrong_max_median"], 2)]],
        )
        + "\n\nA mask removes every wrong joint of a failure only if `tau_kp` is above its highest wrong score.",
    )
    section(
        "Failures that depend on the detector cadence",
        _table(["Cadence label", "Failures"], [[k, str(v)] for k, v in sorted(s["cadence"].items())] or [["n/a", "0"]]),
    )
    cases = s["cases"]
    section(
        "Every failure case (S3 is minor and not counted)",
        _table(
            [
                "ID",
                "Video",
                "Time [s]",
                "Frame",
                "Type",
                "Joints",
                "Sev",
                "View",
                "Situation",
                "Cadence",
                "Score warns",
                "Rules",
            ],
            [
                [
                    c["id"],
                    c["video"],
                    f"{c['t_sec']:.2f}",
                    str(c["frame_index"]),
                    c["type"],
                    ", ".join(c["joints"]) or "-",
                    c["severity"],
                    c["view"],
                    c["situation"],
                    c["cadence"],
                    {True: "yes", False: "no", None: "n/a"}[c["score_warns"]],
                    ", ".join(c["tags"]),
                ]
                for c in cases
            ]
            or [["none"] + [""] * 11],
        ),  # fmt: skip
    )
    return "\n".join(out)
