"""The generator side of the P5.08 cut-off ablation: the truth tables that need the continuous model of
``tests/helpers/synth.py`` (the floor of the speed of a still joint, the pauses against ``slow_intervals``, the hip
range against 2A), and a script that prints them for ``Docs/reports/p5_filter_ablation.md``.

Every run goes through the real chain once per cut-off (``layers_at_cutoffs``, only ``cutoff_hz`` changing). Run from
``taiji_ai/``::

    .venv\\Scripts\\python.exe tests\\helpers\\ablation_sweep.py            # all the tables (about 3 minutes)
    .venv\\Scripts\\python.exe tests\\helpers\\ablation_sweep.py floor      # one of: floor pauses sharp hip
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

if __name__ == "__main__":  # as a script, ``helpers`` is the package next to this file's folder
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from helpers.metric_layers import RECORDING_ID, SOURCES
from helpers.synth import SynthSequence, make_sequence, slow_intervals, speed_at
from taiji_ai.bench.filter_ablation import ALL_CUTOFFS, REFERENCE_HZ, layers_at_cutoffs
from taiji_ai.metrics.hip_height import hip_height_a, hip_height_b
from taiji_ai.metrics.tempo import group_speed
from taiji_ai.quality.layers_io import PoseFiltered

D_MIN = 0.3  # s: the generator's pauses last 0.6 s, the turning point of its movement about 0.2 s
SHARE = 0.10  # tau as a share of the true peak of the group: where the boundary is resolved to about half a step
ABSOLUTE_TAU = 0.3  # body lengths per second: above the floor of a still joint at 1 px of noise


@lru_cache(maxsize=96)
def clip(scenario: str, seed: int, noise_px: float, ramp_s: float | None = None):
    """The sequence and its layers at every cut-off (cached: the same run is read by several tables)."""
    kwargs = {} if ramp_s is None else {"ramp_s": ramp_s}
    seq = make_sequence(scenario, seed=seed, noise_px=noise_px, **kwargs)
    layers = layers_at_cutoffs(
        seq.kp,
        seq.score,
        seq.t_sec,
        recording_id=RECORDING_ID,
        frame_index=np.arange(len(seq.t_sec), dtype=np.int64),
        data_sources=SOURCES,
    )
    return seq, layers


def peak(seq: SynthSequence, group: str) -> float:
    return float(speed_at(seq, np.linspace(0.0, float(seq.params["duration"]), 5001))[group].max())


def speed(layer: PoseFiltered, group: str, **kwargs):
    return group_speed(layer, group=group, flags={}, camera_id="camA", view_category="front", **kwargs)


# --- the floor of the speed of a joint that does not move ------------------------------------------------------------
@dataclass(frozen=True)
class Floor:
    median: float
    p95: float
    maximum: float


def floor(noise_px: float, seeds: tuple[int, ...] = (1, 2, 3), group: str = "hands") -> dict[float, Floor]:
    """SYN-01: the speed of a group over its measured rows, per cut-off: the mean of the medians and of the P95 over the
    seeds and the largest value of all (Lambda per second)."""
    medians: dict[float, list[float]] = {hz: [] for hz in ALL_CUTOFFS}
    p95s: dict[float, list[float]] = {hz: [] for hz in ALL_CUTOFFS}
    maxima: dict[float, list[float]] = {hz: [] for hz in ALL_CUTOFFS}
    for seed in seeds:
        _, layers = clip("SYN-01", seed, noise_px)
        for hz, layer in layers.items():
            s = speed(layer, group).series
            v = np.asarray(s.values)[np.asarray(s.reason) == 0]
            medians[hz].append(float(np.median(v)))
            p95s[hz].append(float(np.percentile(v, 95)))
            maxima[hz].append(float(v.max()))
    return {hz: Floor(float(np.mean(medians[hz])), float(np.mean(p95s[hz])), max(maxima[hz])) for hz in ALL_CUTOFFS}


# --- the pauses against the truth of the continuous profile ----------------------------------------------------------
@dataclass(frozen=True)
class PauseResult:
    found: int
    truth: int
    boundary_steps: float | None  # the largest boundary error in steps when the count is right, else None


def pauses(
    scenario: str,
    seed: int,
    noise_px: float,
    *,
    share: float | None = SHARE,
    tau: float | None = None,
    d_min: float = D_MIN,
    ramp_s: float | None = None,
    group: str = "hands",
) -> dict[float, PauseResult]:
    """The pauses of a group per cut-off against ``slow_intervals`` of the true speed: ``tau`` is ``share`` of the true
    peak of the group, or the absolute ``tau`` when it is given."""
    seq, layers = clip(scenario, seed, noise_px, ramp_s)
    level = tau if tau is not None else float(share) * peak(seq, group)  # type: ignore[arg-type]
    truth = [iv for iv in slow_intervals(seq, group, level) if iv[1] - iv[0] >= d_min]
    out = {}
    for hz, layer in layers.items():
        result = speed(layer, group, pause_tau=level, pause_min_s=d_min)
        events = result.summary.events
        step = result.series.header.step_s
        error = None
        if len(events) == len(truth) and step:
            error = max(
                (max(abs(e.t_start - a), abs(e.t_end - b)) / step for e, (a, b) in zip(events, truth, strict=True)),
                default=0.0,
            )
        out[hz] = PauseResult(found=len(events), truth=len(truth), boundary_steps=error)
    return out


# --- the hip range against the truth ---------------------------------------------------------------------------------
def hip_error(seed: int, noise_px: float, variant: str) -> dict[float, float]:
    """SYN-02: the relative error of the hip range of variant ``A`` or ``B`` against 2A, per cut-off (a fraction)."""
    seq, layers = clip("SYN-02", seed, noise_px)
    whole = [(0.0, float(seq.t_sec[-1]) + 1.0)]
    common = {"stable_intervals": whole, "flags": {}, "camera_id": "camA", "view_category": "front"}
    reference = clip("SYN-01", seed, noise_px)[1] if variant == "A" else None
    out = {}
    for hz, layer in layers.items():
        if variant == "A":
            result = hip_height_a(layer, reference=reference[hz], **common)  # type: ignore[index]
        else:
            result = hip_height_b(layer, **common)
        (stat,) = [s for s in result.summary.statistics if s.name == "hip_height_range"]
        assert stat.value is not None
        out[hz] = stat.value / (2.0 * float(seq.truth["A"])) - 1.0
    return out


# --- the tables of the report ----------------------------------------------------------------------------------------
def _label(hz: float) -> str:
    return "no filter" if hz >= 1000.0 else f"{hz:g} Hz"


def print_floor() -> None:
    print("## Speed floor: SYN-01 (still), the hands, 3 seeds; V in body lengths per second")
    print("| noise | cut-off | median | p95 | max |\n|---|---|---|---|---|")
    for noise in (0.5, 1.0, 2.0):
        for hz, f in floor(noise).items():
            print(f"| {noise:g} px | {_label(hz)} | {f.median:.3f} | {f.p95:.3f} | {f.maximum:.3f} |")


def print_pauses() -> None:
    seeds = (1, 2, 3, 4, 5)
    for scenario in ("SYN-05", "SYN-07"):
        for label, kwargs in (
            ("tau 10 % of the true peak", {"share": SHARE}),
            ("tau 0.3 per second", {"tau": ABSOLUTE_TAU}),
        ):
            print(f"\n## Pauses: {scenario}, hands, {label}, d_min {D_MIN:g} s, seeds {seeds[0]} to {seeds[-1]}")
            print(
                "| noise | cut-off | pauses found per seed (truth) | seeds with the right count | worst error, steps |"
            )
            print("|---|---|---|---|---|")
            for noise in (0.0, 1.0, 2.0):
                rows = {s: pauses(scenario, s, noise, **kwargs) for s in seeds}  # type: ignore[arg-type]
                for hz in ALL_CUTOFFS:
                    found = [rows[s][hz].found for s in seeds]
                    right = sum(rows[s][hz].found == rows[s][hz].truth for s in seeds)
                    errs = [rows[s][hz].boundary_steps for s in seeds if rows[s][hz].boundary_steps is not None]
                    worst = f"{max(errs):.2f}" if errs else "n/a"
                    truth = rows[seeds[0]][hz].truth
                    print(f"| {noise:g} px | {_label(hz)} | {found} ({truth}) | {right} of {len(seeds)} | {worst} |")


def print_sharp() -> None:
    print("\n## Sharp onsets: SYN-05, hands, noise 0, tau 10 % of the true peak, d_min 0.3 s; boundary error in steps")
    print("| ramp | " + " | ".join(_label(hz) for hz in ALL_CUTOFFS) + " |\n|---|" + "---|" * len(ALL_CUTOFFS))
    for ramp in (0.2, 0.1, 0.05, 0.02):
        r = pauses("SYN-05", 1, 0.0, ramp_s=ramp)
        cells = [f"{r[hz].boundary_steps:.2f}" if r[hz].boundary_steps is not None else "n/a" for hz in ALL_CUTOFFS]
        print(f"| {ramp:g} s | " + " | ".join(cells) + " |")


def print_hip() -> None:
    print("\n## Hip range: SYN-02, relative error against 2A (percent), 5 seeds")
    print("| variant | noise | cut-off | per seed | worst |\n|---|---|---|---|---|")
    for variant in ("A", "B"):
        for noise in (0.0, 1.0, 2.0):
            rows = {s: hip_error(s, noise, variant) for s in (1, 2, 3, 4, 5)}
            for hz in ALL_CUTOFFS:
                e = [100.0 * rows[s][hz] for s in rows]
                per_seed = ", ".join(f"{x:.2f}" for x in e)
                print(f"| {variant} | {noise:g} px | {_label(hz)} | {per_seed} | {max(abs(x) for x in e):.2f} |")


if __name__ == "__main__":
    which = sys.argv[1:] or ["floor", "pauses", "sharp", "hip"]
    for name in which:
        {"floor": print_floor, "pauses": print_pauses, "sharp": print_sharp, "hip": print_hip}[name]()
    assert REFERENCE_HZ in ALL_CUTOFFS
