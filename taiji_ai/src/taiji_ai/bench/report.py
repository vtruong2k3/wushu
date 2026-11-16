"""Render the tables of the pose benchmark report (P3.07) from the result of ``run_benchmark``.

Every number of the report's tables comes from this function, so none is typed by hand; the analysis around the tables
is written by a person and refers to them. A value that was not measured is printed ``n/a`` (never 0). Pure function:
no I/O.
"""

from __future__ import annotations

from typing import Any

DRIFT_UNCERTAIN_MIB = 300.0  # a baseline that moved more than this makes the VRAM figure uncertain


def _f(x: float | int | None, digits: int = 3) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, int):
        return str(x)
    return f"{x:.{digits}f}"


def _pct(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{100.0 * x:.{digits}f} %"


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _stats(s: dict[str, float] | None, keys: tuple[str, ...], digits: int) -> list[str]:
    return [_f(None if s is None else s[k], digits) for k in keys]


def render_tables(result: dict[str, Any]) -> str:
    """The markdown tables of the report, in the order the report discusses them."""
    ns: list[int] = result["ns"]
    runs = result["runs"]
    clips = result["clips"]
    env = result["environment"]
    out: list[str] = []

    def section(title: str, body: str) -> None:
        out.append(f"### {title}\n\n{body}\n")

    section(
        "Machine and software",
        _table(
            ["Item", "Value"],
            [
                ["Date", env["date"]],
                ["GPU", _f(None) if env["gpu"] is None else f"{env['gpu']}, {_f(env['gpu_total_mib'], 0)} MiB"],
                ["Driver", _f(None) if env["driver"] is None else env["driver"]],
                ["onnxruntime-gpu / rtmlib", f"{env['onnxruntime_gpu']} / {env['rtmlib']}"],
                ["PyAV / numpy / Python", f"{env['av']} / {env['numpy']} / {env['python']}"],
                ["Providers", ", ".join(f"{k}: {v}" for k, v in env["providers"].items())],
                [
                    "GPU utilisation before each run (other programs)",
                    ", ".join(f"N={n}: {_f(env['utilisation_before_pct'][str(n)], 0)} %" for n in ns),
                ],
            ],
        ),
    )

    section(
        "Clips",
        _table(
            ["Clip", "Video", "Start [s]", "Frames", "Codec", "fps", "Size", "Persons per frame: 0 / 1 / 2 / 3 / 4+"],
            [
                [
                    cid,
                    c["video"],
                    _f(c["start_s"], 0),
                    str(c["n_frames"]),
                    c["codec"],
                    _f(c["nominal_fps"], 2),
                    f"{c['width']}x{c['height']}",
                    " / ".join(_pct(c["persons_per_frame"][k], 0) for k in ("0", "1", "2", "3", "4+")),
                ]
                for cid, c in clips.items()
            ],
        ),
    )

    rows = []
    for cid in clips:
        row = [cid]
        for n in ns:
            c = runs[str(n)]["summary"]["per_clip"][cid]
            row.append(
                f"{_f(c['rtf_median'])} ({_f(c['rtf_min'])} to {_f(c['rtf_max'])})" + (" noisy" if c["noisy"] else "")
            )
        rows.append(row)
    rows.append(["all clips"] + [_f(runs[str(n)]["summary"]["rtf"]) for n in ns])
    section(
        "Real-time factor (median of the measured passes, minimum to maximum)",
        _table(["Clip"] + [f"N = {n}" for n in ns], rows),
    )

    rows = []
    for n in ns:
        s = runs[str(n)]["summary"]
        p = s["phases_s"]
        total = s["elapsed_median_s"]
        rows.append(
            [f"N = {n}", _f(total, 2)]
            + [f"{_f(p[k], 2)} ({_pct(p[k] / total, 0)})" for k in ("decode_s", "detect_s", "estimate_s", "other_s")]
            + [_f(p["post_s"], 2)]
        )
    section(
        "Where the time goes (seconds for one pass over all the clips; the share of the elapsed time in brackets)",
        _table(["N", "Elapsed", "Decode", "Detector", "Pose", "Other", "After run_pose (not in elapsed)"], rows),
    )

    rows = []
    for n in ns:
        s = runs[str(n)]["summary"]
        lat, win = s["frame_latency_ms"], s["window_rtf"]
        rows.append(
            [
                f"N = {n}",
                _f(s["ms_per_frame"], 1),
                _f(lat["50"], 1),
                _f(lat["95"], 1),
                _f(lat["99"], 1),
                _f(win["50"]),
                _f(win["95"]),
                str(s["n_windows"]),
                _f(s["rtf_at_30_fps"]),
                _f(s["rtf_at_60_fps"]),
            ]
        )
    section(
        "Per-frame latency and real-time factor over 1 s windows (B-PERF-01)",
        _table(
            [
                "N",
                "Mean ms/frame",
                "Frame p50",
                "Frame p95",
                "Frame p99",
                "Window RTF p50",
                "Window RTF p95",
                "Windows",
                "RTF at 30 fps",
                "RTF at 60 fps",
            ],
            rows,
        ),  # fmt: skip
    )

    rows = []
    for n in ns:
        v = runs[str(n)]["worker"]["vram"]
        if not v["measured"]:
            rows.append([f"N = {n}", "not measured", v["reason"] or "", "", "", "", ""])
            continue
        flag = " (uncertain)" if v["drift_mib"] > DRIFT_UNCERTAIN_MIB else ""
        peaks = v["peaks_mib"]
        rows.append(
            [
                f"N = {n}",
                _f(v["baseline_mib"], 0),
                _f(v["drift_mib"], 0),
                _f(peaks.get("warmup"), 0),
                _f(peaks.get("measured"), 0),
                _f(v["peak_delta_mib"], 0) + flag,
                _f(v["total_mib"] - v["peak_total_mib"], 0),
            ]
        )
    section(
        "GPU memory (device total in MiB, one fresh process per N)",
        _table(
            [
                "N",
                "Baseline",
                "Baseline drift",
                "Peak in warm-up",
                "Peak in measured passes",
                "Peak minus baseline",
                "Free at the peak",
            ],
            rows,
        ),  # fmt: skip
    )

    rows = []
    first_clip = next(iter(clips))
    for n in ns:
        w = runs[str(n)]["worker"]
        steady = runs[str(n)]["summary"]["per_clip"][first_clip]["elapsed_median_s"]
        rows.append([f"N = {n}", _f(w["load_s"], 2), _f(w["warmup"]["elapsed_s"], 2), _f(steady, 2)])
    section(
        f"Cold start (model load, warm-up pass and the steady pass of clip {first_clip}, seconds)",
        _table(["N", "Model load", "Warm-up pass", "Steady pass"], rows),
    )

    rows = []
    for cid in clips:
        rows.append([cid] + [_f(runs[str(n)]["summary"]["per_clip"][cid]["end_to_end_s"], 1) for n in ns])
    section(
        "Pose stage of one 30 s segment (run_pose with its 1 s margins, association, target, track, saving), seconds",
        _table(["Clip"] + [f"N = {n}" for n in ns], rows),
    )

    others = [n for n in ns if n != 1]
    if others:
        rows = []
        for n in others:
            e = result["effect"][str(n)]["pooled"]
            delay = e["entry_delay_frames"]
            rows.append(
                [
                    f"N = {n}",
                    _pct(e["count_agreement"], 2),
                    str(e["n_pairs"]),
                    str(e["n_missed"]),
                    str(e["n_extra"]),
                    f"{e['n_uncomparable_ref']} / {e['n_uncomparable_other']}",
                    f"{_f(delay['mean'], 2)} / {_f(delay['max'])}",
                    str(e["n_tracks_never_matched"]),
                ]
            )
        section(
            "Effect of N against N = 1: persons (all clips pooled)",
            _table(
                [
                    "N",
                    "Frames with the same count",
                    "Matched",
                    "Missed",
                    "Extra",
                    "Uncomparable (N=1 / N)",
                    "Entry delay mean / max [frames]",
                    "Tracks never matched",
                ],
                rows,
            ),  # fmt: skip
        )
        rows = []
        for n in others:
            e = result["effect"][str(n)]["pooled"]
            rows.append(
                [f"N = {n}"]
                + _stats(e["px"], ("median", "p95", "p99", "max"), 2)
                + _stats(e["norm"], ("median", "p95", "p99", "max"), 4)
            )
        section(
            "Effect of N against N = 1: keypoint distance (all clips pooled; pixels, then body heights)",
            _table(
                ["N", "px median", "px p95", "px p99", "px max", "body median", "body p95", "body p99", "body max"],
                rows,
            ),
        )
        groups = ["head", "trunk", "arms", "legs", "feet"]
        rows = [
            [f"N = {n}"] + [_f(result["effect"][str(n)]["pooled"]["group_p95_norm"][g], 4) for g in groups]
            for n in others
        ]
        section("p95 distance per joint group (body heights)", _table(["N"] + groups, rows))

        rows = []
        for n in others:
            for cid, c in result["effect"][str(n)]["per_clip"].items():
                comp, down = c["comparison"], c["downstream"]
                rows.append(
                    [
                        f"N = {n}",
                        cid,
                        _pct(comp["count_agreement"], 2),
                        f"{comp['n_missed']} / {comp['n_extra']}",
                        _f(None if comp["norm"] is None else comp["norm"]["p95"], 4),
                        _f(None if comp["px"] is None else comp["px"]["max"], 1),
                        {True: "yes", False: "no", None: "n/a"}[c["same_target"]],
                        _pct(down["share_tracked"], 2),
                        {True: "yes", False: "no", None: "n/a"}[down["needs_reselect"]],
                    ]
                )
        for cid in clips:
            ref = result["reference"][cid]
            rows.append(
                ["N = 1", cid, "reference", "", "", "", "reference", _pct(ref["share_tracked"], 2),
                 {True: "yes", False: "no", None: "n/a"}[ref["needs_reselect"]]]
            )  # fmt: skip
        section(
            "Effect of N per clip, and what the target looks like downstream",
            _table(
                [
                    "N",
                    "Clip",
                    "Same count",
                    "Missed / extra",
                    "p95 body",
                    "Max px",
                    "Same target",
                    "Tracked share",
                    "needs_reselect",
                ],
                rows,
            ),  # fmt: skip
        )

        rows = []
        for n in others:
            t = result["effect"][str(n)]["target_pooled"]
            if t is None:
                rows.append([f"N = {n}", "no target in either run"] + [""] * 12)
                continue
            rows.append(
                [f"N = {n}", str(t["n_frames"]), str(t["n_both_tracked"]), str(t["n_ref_only"]), str(t["n_other_only"]),
                 str(t["n_uncomparable_frames"])]
                + _stats(t["px"], ("median", "p95", "p99", "max"), 2)
                + _stats(t["norm"], ("median", "p95", "p99", "max"), 4)
            )  # fmt: skip
        section(
            "Supplementary: the target track that P4 receives, N against N = 1 "
            "(added after the dry run; not part of the rule)",
            _table(
                [
                    "N",
                    "Frames",
                    "Both have the target",
                    "Only N = 1",
                    "Only N",
                    "Uncomparable",
                    "px median",
                    "px p95",
                    "px p99",
                    "px max",
                    "body median",
                    "body p95",
                    "body p99",
                    "body max",
                ],
                rows,
            ),
        )

    rule = result["rule"]
    rec = result["recommendation"]
    rows = []
    for n in others:
        reasons = rec["reasons"][str(n)]
        rows.append(
            [
                f"N = {n}",
                "yes" if rec["acceptable"][str(n)] else "no",
                _pct(rec["speed_gain_vs_previous"][str(n)], 1),
                "; ".join(reasons) if reasons else "all criteria met",
            ]
        )
    body = _table(["N", "Acceptable", "Faster than the previous N by", "Why not"], rows) if rows else "only N = 1"
    section(
        "The rule written before the measurement, and its result",
        f"Limits: agreement at least {_pct(rule['min_count_agreement'], 1)}; "
        f"p95 at most {rule['max_p95_norm']} and p99 at most {rule['max_p99_norm']} body heights; "
        f"tracked share not lower by more than {rule['max_tracked_loss_points']} "
        f"points; no new needs_reselect; a larger N must be at least {_pct(rule['min_speed_gain'], 0)} faster than the "
        f"previous one.\n\n{body}\n\n**Recommended N: {rec['n']}**",
    )
    return "\n".join(out)
