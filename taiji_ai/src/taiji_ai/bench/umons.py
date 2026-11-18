"""The UMONS-TAICHI Kinect recordings as input of the quality chain (P4.08): a strict reader, the mapping to the layers
the chain reads, the run over a folder, and the numbers.

**Third-party data, internal development only.** UMONS-TAICHI (D12) is CC BY-NC-SA 4.0 and tagged ``dev-test`` and
``benchmark`` in ``Docs/DATASET_REGISTRY_TAIJI.md``; it is 13 techniques, not the 24 forms, so nothing here is a product
number (AGENTS.md 9.4.4). This module lives in ``bench/`` and is never imported by the product path. Only counts, shares
and the dataset's own sequence ids (``P01T01C03``) leave it; no value of a file is stored or printed.

**The file.** One row per frame: a timestamp in **ms** and 25 joints x (x, y, z) in **mm**, 76 numbers, the joints in
the order of the Kinect V2 ``JointType`` (``KINECT_JOINTS``). ``z`` is vertical, ``y`` lateral, ``x`` the distance
along the sensor axis (checked on the data: the median torso keeps 97 to 100 % of its length in the plane (y, z)).

**The rules** (``Docs/tasks/P4.08.md``):

1. The reader is strict: exactly 76 finite numbers per non-empty line, at least one row, timestamps that never decrease;
   an error names the sequence and the line of the file, never a path.
2. The clock is the file's own, in seconds from the first row: nothing is regularised and no frame rate is assumed
   (AGENTS.md 5.2). A timestamp that occurs **more than once** means two bodies in one frame (found in one file, the
   rows alternate between two skeletons 650 mm apart) and the file does not say which is the performer: the **first**
   row of the timestamp is kept as ``tracked = False`` (the chain sees ``not_tracked`` and never bridges it, as W5's
   ``ambiguous``), the others are dropped and counted.
3. 17 of the 26 HALPE joints exist in Kinect (``KINECT_TO_HALPE``; the foot is the nearest to the big toe, an
   approximation); the spine mid, spine shoulder, hands, hand tips and thumbs have no HALPE joint; the nine others
   (nose, eyes, ears, small toes, heels) are NaN with a NaN score, so the chain reports them ``non_finite``.
4. The position is ``(y, -z)`` in mm read as pixels (x to the right, y down): no calibration is invented, and the stages
   are scale-free (the Hampel floor and the swap limit are torso lengths, gaps, grid and filter are in seconds).
5. The file has **no confidence**: a joint it reports gets the score **1.0** (a convention that says "reported", not a
   probability); a joint at exactly (0, 0, 0), the only "not tracked" marker, keeps the file's value with the score
   **0.0** (the mask makes it NaN, ``low_conf``).
"""

from __future__ import annotations

import csv
import io
import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np

from taiji_ai.bench import BenchError
from taiji_ai.pose.skeleton import IDX, JOINTS, NUM_JOINTS
from taiji_ai.quality import QualityError
from taiji_ai.quality.chain import QualityParams, run_quality_arrays
from taiji_ai.schemas.quality import IntervalCoverage, QualityReport
from taiji_ai.store.artifacts import atomic_write_text

log = logging.getLogger(__name__)

KINECT_JOINTS: Final[tuple[str, ...]] = (
    "SpineBase", "SpineMid", "Neck", "Head", "ShoulderLeft", "ElbowLeft", "WristLeft", "HandLeft",
    "ShoulderRight", "ElbowRight", "WristRight", "HandRight", "HipLeft", "KneeLeft", "AnkleLeft", "FootLeft",
    "HipRight", "KneeRight", "AnkleRight", "FootRight", "SpineShoulder", "HandTipLeft", "ThumbLeft", "HandTipRight",
    "ThumbRight",
)  # fmt: skip
KINECT_TO_HALPE: Final[dict[str, str]] = {
    "SpineBase": "Hip", "Neck": "Neck", "Head": "Head",
    "ShoulderLeft": "LShoulder", "ElbowLeft": "LElbow", "WristLeft": "LWrist",
    "ShoulderRight": "RShoulder", "ElbowRight": "RElbow", "WristRight": "RWrist",
    "HipLeft": "LHip", "KneeLeft": "LKnee", "AnkleLeft": "LAnkle", "FootLeft": "LBigToe",
    "HipRight": "RHip", "KneeRight": "RKnee", "AnkleRight": "RAnkle", "FootRight": "RBigToe",
}  # fmt: skip
PROVIDED: Final[tuple[int, ...]] = tuple(sorted(IDX[halpe] for halpe in KINECT_TO_HALPE.values()))

N_FIELDS: Final = 76  # a timestamp and 25 joints x (x, y, z)
N_KINECT_JOINTS: Final = 25
EXPECTED_FILES: Final = 111  # the Kinect files of the dataset (Zenodo 2784581)
LONG_STEP_FACTOR: Final = 1.5  # a step longer than this many median steps (and not a pause) is a dropped frame
SCORE_REPORTED: Final = 1.0
SCORE_ZERO_JOINT: Final = 0.0

_ID = re.compile(r"P\d{2}T\d{2}C\d{2}")
_FILE = re.compile(r"P\d{2}T\d{2}C\d{2}\.txt")
_LICENSE_FILE = "License.txt"
_LICENSE_MARK = "CC BY-NC-SA"
_KINECT_INDEX: Final = {name: i for i, name in enumerate(KINECT_JOINTS)}
_REASONS: Final = ("low_conf", "non_finite", "not_tracked", "frame_invalid", "outlier", "no_frame")
_OUTCOMES: Final = ("filled", "too_long", "never_fill", "blocked", "open_start", "open_end", "open_both")


class UmonsError(BenchError):
    """A UMONS file or folder is not what the adapter expects; the message names the sequence and row, never a path."""


def _frozen(a: np.ndarray) -> np.ndarray:
    a.setflags(write=False)
    return a


def _check_id(sequence_id: object) -> str:
    if not isinstance(sequence_id, str) or not _ID.fullmatch(sequence_id):
        raise UmonsError(f"sequence id must be a dataset id like P01T01C03, got {sequence_id!r}")
    return sequence_id


@dataclass(frozen=True, eq=False)
class KinectSequence:
    """One Kinect recording as the layers the quality chain reads; every array is read-only (``T`` rows)."""

    sequence_id: str
    t_sec: np.ndarray  # (T,) float64 [s] from the first row, strictly increasing
    keypoints: np.ndarray  # (T, 26, 2) float32 [mm read as pixels]: (y, -z); NaN for a joint the file does not have
    scores: np.ndarray  # (T, 26) float32: 1.0 reported, 0.0 at (0, 0, 0), NaN for a joint the file does not have
    tracked: np.ndarray  # (T,) bool: False where two bodies shared the timestamp
    rows_in_file: int  # the non-empty lines of the file
    repeated_rows: int  # rows dropped because their timestamp had a row already
    ambiguous_timestamps: int  # timestamps used by more than one row (the kept row is not tracked)
    zero_joint_cells: int  # cells of the 17 joints of the layer that are exactly (0, 0, 0), in the rows kept


def parse_kinect(text: str, sequence_id: str) -> KinectSequence:
    """The layers of a Kinect file's text; see the module docstring for the rules.

    Raises ``UmonsError`` naming ``sequence_id`` and the line of the file for a row that is not 76 finite numbers, a
    timestamp that decreases, a text without rows, or an id that is not a dataset id.
    """
    sid = _check_id(sequence_id)
    lines = [(n, raw.split()) for n, raw in enumerate(text.splitlines(), start=1) if raw.strip()]
    if not lines:
        raise UmonsError(f"{sid}: the file has no rows")
    for n, tokens in lines:
        if len(tokens) != N_FIELDS:
            raise UmonsError(f"{sid}: row {n}: expected {N_FIELDS} numbers, got {len(tokens)}")
    try:
        flat = np.array([token for _, tokens in lines for token in tokens], dtype=np.float64)
    except ValueError:
        for n, tokens in lines:  # find the row for the message
            for token in tokens:
                try:
                    float(token)
                except ValueError:
                    raise UmonsError(f"{sid}: row {n}: {token!r} is not a number") from None
        raise  # pragma: no cover - numpy refused what Python accepts: not expected
    rows = flat.reshape(len(lines), N_FIELDS)
    finite = np.isfinite(rows).all(axis=1)
    if not finite.all():
        n = lines[int(np.argmin(finite))][0]
        raise UmonsError(f"{sid}: row {n}: a value is not finite")
    ts = rows[:, 0]
    step = np.diff(ts)
    if (step < 0).any():
        r = int(np.argmax(step < 0)) + 1
        raise UmonsError(f"{sid}: row {lines[r][0]}: the timestamp decreases ({ts[r - 1]:g} ms, then {ts[r]:g} ms)")
    repeats = np.zeros(len(ts), dtype=bool)
    repeats[1:] = step == 0
    keep = ~repeats
    shared_with_next = np.zeros(len(ts), dtype=bool)
    shared_with_next[:-1] = step == 0
    ambiguous = shared_with_next[keep]  # the kept row's timestamp is also used by the rows after it
    xyz = rows[keep][:, 1:].reshape(-1, N_KINECT_JOINTS, 3)
    n_rows = xyz.shape[0]
    zero = (xyz == 0.0).all(axis=2)
    keypoints = np.full((n_rows, NUM_JOINTS, 2), np.nan, dtype=np.float32)
    scores = np.full((n_rows, NUM_JOINTS), np.nan, dtype=np.float32)
    zero_cells = 0
    for kinect, halpe in KINECT_TO_HALPE.items():
        k, h = _KINECT_INDEX[kinect], IDX[halpe]
        keypoints[:, h, 0] = xyz[:, k, 1]
        keypoints[:, h, 1] = -xyz[:, k, 2]
        scores[:, h] = np.where(zero[:, k], SCORE_ZERO_JOINT, SCORE_REPORTED)
        zero_cells += int(zero[:, k].sum())
    return KinectSequence(
        sequence_id=sid,
        t_sec=_frozen((ts[keep] - ts[0]) / 1000.0),
        keypoints=_frozen(keypoints),
        scores=_frozen(scores),
        tracked=_frozen(~ambiguous),
        rows_in_file=len(lines),
        repeated_rows=int(repeats.sum()),
        ambiguous_timestamps=int(ambiguous.sum()),
        zero_joint_cells=zero_cells,
    )


def load_kinect(path: str | Path) -> KinectSequence:
    """Read a Kinect file; its sequence id is the file stem. Raises ``FileNotFoundError`` and ``UmonsError``."""
    file = Path(path)
    sid = _check_id(file.stem)
    try:
        text = file.read_text(encoding="ascii")
    except UnicodeDecodeError:
        raise UmonsError(f"{sid}: the file is not ASCII text") from None
    return parse_kinect(text, sid)


def find_umons(root: str | Path) -> Path:
    """The folder of the 111 Kinect files, from the dataset root, its ``extracted`` folder or the folder itself.

    Checks that the folder holds nothing but ``License.txt`` and files ``PxxTxxCxx.txt``, that there are exactly 111 of
    them and that the license names CC BY-NC-SA. Raises ``UmonsError`` (the message names no path).
    """
    base = Path(root)
    if not base.is_dir():
        raise UmonsError("the UMONS folder does not exist")
    for candidate in (base, base / "Kinect", base / "extracted" / "Kinect"):
        if candidate.is_dir() and any(_FILE.fullmatch(p.name) or p.name == _LICENSE_FILE for p in candidate.iterdir()):
            folder = candidate
            break
    else:
        raise UmonsError(f"no Kinect folder found: expected files PxxTxxCxx.txt and {_LICENSE_FILE}")
    count = 0
    for entry in sorted(folder.iterdir()):
        if entry.name == _LICENSE_FILE:
            continue
        if not (entry.is_file() and _FILE.fullmatch(entry.name)):
            # the name of an entry is free text of the user's disk: it is not echoed (BUG-0082)
            raise UmonsError(
                f"unexpected entry in the Kinect folder: only PxxTxxCxx.txt and {_LICENSE_FILE} are expected"
            )
        count += 1
    if count != EXPECTED_FILES:
        raise UmonsError(f"expected {EXPECTED_FILES} files PxxTxxCxx.txt, found {count}")
    license_file = folder / _LICENSE_FILE
    if not license_file.is_file():
        raise UmonsError(f"{_LICENSE_FILE} is missing")
    if _LICENSE_MARK not in license_file.read_text(encoding="utf-8", errors="replace"):
        raise UmonsError(f"{_LICENSE_FILE} does not name {_LICENSE_MARK} 4.0")
    return folder


@dataclass(frozen=True, eq=False)
class SequenceResult:
    """The numbers of one file: the adapter's counts, the clock's, Hampel's and the report of the chain.

    A file that failed has ``report`` None and ``error`` set; the counts are then 0 and mean nothing.
    """

    sequence_id: str
    rows_in_file: int = 0
    repeated_rows: int = 0
    ambiguous_timestamps: int = 0
    zero_joint_cells: int = 0
    duration_s: float = 0.0  # [s] first to last row
    steps_long: int = 0  # steps over 1.5 median steps that are not a pause: dropped frames
    steps_pause: int = 0  # steps over the gap limit of the chain (0.150 s): the grid has no frame there
    max_step_s: float = 0.0  # [s]
    hampel_outliers: tuple[int, ...] = ()  # per HALPE joint, cells Hampel set to NaN, on the rows of the file
    report: QualityReport | None = None
    error: str | None = None
    seconds: float = 0.0  # [s] the chain and its report


def run_sequence(sequence: KinectSequence, params: QualityParams | None = None) -> SequenceResult:
    """The quality chain over one sequence (``run_quality_arrays``, its ``tracked``, one segment)."""
    params = QualityParams() if params is None else params
    started = time.perf_counter()
    result = run_quality_arrays(
        sequence.keypoints, sequence.scores, sequence.t_sec, tracked=sequence.tracked, params=params
    )
    seconds = time.perf_counter() - started
    steps = np.diff(sequence.t_sec)
    pause = params.gaps.max_gap_s
    if len(steps):
        median = float(np.median(steps))
        steps_long = int(((steps > LONG_STEP_FACTOR * median) & (steps <= pause)).sum())
        steps_pause = int((steps > pause).sum())
        max_step = float(steps.max())
    else:
        steps_long = steps_pause = 0
        max_step = 0.0
    return SequenceResult(
        sequence_id=sequence.sequence_id,
        rows_in_file=sequence.rows_in_file,
        repeated_rows=sequence.repeated_rows,
        ambiguous_timestamps=sequence.ambiguous_timestamps,
        zero_joint_cells=sequence.zero_joint_cells,
        duration_s=float(sequence.t_sec[-1]) if len(sequence.t_sec) else 0.0,
        steps_long=steps_long,
        steps_pause=steps_pause,
        max_step_s=max_step,
        hampel_outliers=tuple(int(v) for v in result.hampel.outlier.sum(axis=0)),
        report=result.report,
        seconds=seconds,
    )


def run_folder(
    folder: str | Path, params: QualityParams | None = None, names: Sequence[str] | None = None
) -> list[SequenceResult]:
    """Run the chain over the files of ``folder`` (or the named ones), sorted by id.

    A file that fails the reader or the chain is an **error row** (its id, the exception and its message), never a skip.
    Raises ``UmonsError`` for a name that is not a sequence id or not in the folder (before anything runs).
    """
    files = {p.stem: p for p in Path(folder).iterdir() if _FILE.fullmatch(p.name)}
    if names is None:
        selected = sorted(files)
    else:
        for name in names:
            if not isinstance(name, str) or not _ID.fullmatch(name):
                raise UmonsError(f"{name!r} is not a sequence id")
            if name not in files:
                raise UmonsError(f"sequence {name} is not in the folder")
        selected = sorted(set(names))
    results: list[SequenceResult] = []
    for name in selected:
        try:
            results.append(run_sequence(load_kinect(files[name]), params))
        except UmonsError as exc:
            results.append(SequenceResult(name, error=str(exc)))
        except QualityError as exc:
            results.append(SequenceResult(name, error=f"{name}: {type(exc).__name__}: {exc}"))
    log.info("umons run: %d files, %d failed", len(results), sum(r.error is not None for r in results))
    return results


Distribution = tuple[float, float, float, float]  # min, p10, median, max


def _distribution(values: Sequence[float]) -> Distribution:
    if not values:
        nan = float("nan")
        return (nan, nan, nan, nan)
    v = np.asarray(values, dtype=np.float64)
    return (float(v.min()), float(np.percentile(v, 10)), float(np.median(v)), float(v.max()))


@dataclass(frozen=True, eq=False)
class UmonsSummary:
    """The numbers of a run over many files: sums of the reports and distributions over the files."""

    files: int  # files that ran
    errors: tuple[tuple[str, str], ...]  # (sequence id, message) of the files that failed
    rows_in_file: int
    rows: int  # rows after the repeated timestamps were dropped
    repeated_rows: int
    ambiguous_timestamps: int
    zero_joint_cells: int
    steps_long: int
    steps_pause: int
    max_step_s: float
    grid_rows: int
    resampled_files: int
    mixed_rows: int
    cells: int  # grid rows x 26
    observed: int
    bridged: int
    missing: int
    provided_cells: int  # grid rows x 17: the joints that Kinect has
    provided_observed: int
    provided_bridged: int
    provided_missing: int
    unobserved_by_reason: dict[str, int]
    missing_by_reason: dict[str, int]
    gap_gaps: dict[str, int]
    gap_cells: dict[str, int]
    usable_frames: int
    not_tracked_frames: int
    filtered: int
    unfiltered: int
    suspect: int
    blocked: int
    swap_warnings: int
    hampel_by_joint: dict[str, int]  # the 17 joints of the layer: cells Hampel set to NaN, on the rows of the files
    hampel_outliers: int  # the same, summed
    seconds: float
    usable_frames_share: Distribution  # per file: usable frames / grid rows
    provided_usable_share: Distribution  # per file: observed + bridged cells of the 17 joints / their cells
    mixed_share: Distribution  # per file: mixed grid rows / grid rows
    outlier_share: Distribution  # per file: Hampel cells of the 17 joints / (rows x 17)
    torso_mm: Distribution  # per file: the median torso in the plane [mm]
    step_ms: Distribution  # per file: the step of the grid [ms]
    notable: dict[str, object]


def _provided(seg: IntervalCoverage) -> tuple[int, int, int]:
    names = {JOINTS[j] for j in PROVIDED}
    chosen = [j for j in seg.joints if j.joint in names]
    return (sum(j.observed for j in chosen), sum(j.bridged for j in chosen), sum(j.missing for j in chosen))


def _count_dict(names: Sequence[str]) -> dict[str, int]:
    return dict.fromkeys(names, 0)


def aggregate(results: Sequence[SequenceResult]) -> UmonsSummary:
    """Sum the reports of the files that ran and take the distributions over them; failed files are listed apart."""
    ran = [(r, r.report) for r in results if r.report is not None]
    ok = [r for r, _ in ran]
    errors = tuple((r.sequence_id, r.error or "") for r in results if r.report is None)
    sums = dict.fromkeys(
        ("rows", "grid_rows", "resampled", "mixed", "cells", "observed", "bridged", "missing", "p_obs", "p_br", "p_mi")
        + ("usable", "not_tracked", "filtered", "unfiltered", "suspect", "blocked", "swap", "hampel"),
        0,
    )
    unobserved, missing_by = _count_dict(_REASONS), _count_dict(_REASONS)
    gap_gaps, gap_cells = _count_dict(_OUTCOMES), _count_dict(_OUTCOMES)
    hampel_joint = dict.fromkeys((JOINTS[j] for j in PROVIDED), 0)
    shares: dict[str, list[float]] = {k: [] for k in ("usable", "provided", "mixed", "outlier", "torso", "step")}
    named: dict[str, list[str]] = {k: [] for k in ("ambiguous", "zero_joint", "no_frame", "swap")}
    for r, rep in ran:
        seg = rep.intervals[0]
        p_obs, p_br, p_mi = _provided(seg)
        sums["rows"] += seg.source_rows
        sums["grid_rows"] += seg.rows
        sums["resampled"] += int(rep.timeline.resampled)
        sums["mixed"] += seg.mixed_rows
        for key, value in (("cells", seg.cells), ("observed", seg.observed), ("bridged", seg.bridged)):
            sums[key] += value
        sums["missing"] += seg.missing
        sums["p_obs"] += p_obs
        sums["p_br"] += p_br
        sums["p_mi"] += p_mi
        sums["usable"] += seg.usable_frames
        sums["not_tracked"] += seg.not_tracked_frames
        sums["filtered"] += seg.filtered
        sums["unfiltered"] += seg.unfiltered
        sums["suspect"] += seg.suspect
        sums["blocked"] += seg.blocked
        swaps = sum(w.startswith("lr_swap_suspect@") for w in rep.warnings)
        sums["swap"] += swaps
        for name, value in seg.unobserved_by_reason.model_dump().items():
            unobserved[name] += value
        for name, value in seg.missing_by_reason.model_dump().items():
            missing_by[name] += value
        for name, value in seg.gaps.gaps.model_dump().items():
            gap_gaps[name] += value
        for name, value in seg.gaps.cells.model_dump().items():
            gap_cells[name] += value
        outliers = 0
        for j in PROVIDED:
            hampel_joint[JOINTS[j]] += r.hampel_outliers[j]
            outliers += r.hampel_outliers[j]
        sums["hampel"] += outliers
        n_p = len(PROVIDED)
        shares["usable"].append(seg.usable_frames / seg.rows if seg.rows else float("nan"))
        shares["provided"].append((p_obs + p_br) / (n_p * seg.rows) if seg.rows else float("nan"))
        shares["mixed"].append(seg.mixed_rows / seg.rows if seg.rows else float("nan"))
        shares["outlier"].append(outliers / (n_p * seg.source_rows) if seg.source_rows else float("nan"))
        if rep.timeline.torso_px is not None:
            shares["torso"].append(rep.timeline.torso_px)
        if rep.timeline.step_s is not None:
            shares["step"].append(rep.timeline.step_s * 1000.0)
        if r.ambiguous_timestamps:
            named["ambiguous"].append(r.sequence_id)
        if r.zero_joint_cells:
            named["zero_joint"].append(r.sequence_id)
        if seg.missing_by_reason.no_frame:
            named["no_frame"].append(r.sequence_id)
        if swaps:
            named["swap"].append(r.sequence_id)
    notable: dict[str, object] = {key: sorted(ids) for key, ids in named.items()}
    if ok:
        notable["longest"] = max(ran, key=lambda pair: pair[1].intervals[0].source_rows)[0].sequence_id
        notable["largest_step"] = max(ok, key=lambda r: r.max_step_s).sequence_id
        by_provided = {r.sequence_id: s for r, s in zip(ok, shares["provided"], strict=True)}
        by_usable = {r.sequence_id: s for r, s in zip(ok, shares["usable"], strict=True)}
        by_outlier = {r.sequence_id: s for r, s in zip(ok, shares["outlier"], strict=True)}
        notable["lowest_provided"] = min(by_provided, key=lambda k: by_provided[k])
        notable["lowest_usable_frames"] = min(by_usable, key=lambda k: by_usable[k])
        notable["most_outliers"] = max(by_outlier, key=lambda k: by_outlier[k])
    return UmonsSummary(
        files=len(ok),
        errors=errors,
        rows_in_file=sum(r.rows_in_file for r in ok),
        rows=sums["rows"],
        repeated_rows=sum(r.repeated_rows for r in ok),
        ambiguous_timestamps=sum(r.ambiguous_timestamps for r in ok),
        zero_joint_cells=sum(r.zero_joint_cells for r in ok),
        steps_long=sum(r.steps_long for r in ok),
        steps_pause=sum(r.steps_pause for r in ok),
        max_step_s=max((r.max_step_s for r in ok), default=0.0),
        grid_rows=sums["grid_rows"],
        resampled_files=sums["resampled"],
        mixed_rows=sums["mixed"],
        cells=sums["cells"],
        observed=sums["observed"],
        bridged=sums["bridged"],
        missing=sums["missing"],
        provided_cells=sums["grid_rows"] * len(PROVIDED),
        provided_observed=sums["p_obs"],
        provided_bridged=sums["p_br"],
        provided_missing=sums["p_mi"],
        unobserved_by_reason=unobserved,
        missing_by_reason=missing_by,
        gap_gaps=gap_gaps,
        gap_cells=gap_cells,
        usable_frames=sums["usable"],
        not_tracked_frames=sums["not_tracked"],
        filtered=sums["filtered"],
        unfiltered=sums["unfiltered"],
        suspect=sums["suspect"],
        blocked=sums["blocked"],
        swap_warnings=sums["swap"],
        hampel_by_joint=hampel_joint,
        hampel_outliers=sums["hampel"],
        seconds=sum(r.seconds for r in ok),
        usable_frames_share=_distribution(shares["usable"]),
        provided_usable_share=_distribution(shares["provided"]),
        mixed_share=_distribution(shares["mixed"]),
        outlier_share=_distribution(shares["outlier"]),
        torso_mm=_distribution(shares["torso"]),
        step_ms=_distribution(shares["step"]),
        notable=notable,
    )


def _pct(part: int, whole: int, digits: int = 2) -> str:
    return f"{100.0 * part / whole:.{digits}f} %" if whole else "n/a"


def _dist(d: Distribution, scale: float = 100.0, unit: str = " %", digits: int = 2) -> str:
    return " / ".join(f"{v * scale:.{digits}f}" for v in d) + unit


MAX_IDS = 10  # a list of sequence ids longer than this is shown as a count and its first ids


def _ids(value: object) -> str:
    if not isinstance(value, list):
        return str(value)
    if len(value) > MAX_IDS:
        return f"{len(value)} files, the first {MAX_IDS}: " + ", ".join(value[:MAX_IDS])
    return ", ".join(value)


def render_tables(runs: Mapping[str, UmonsSummary]) -> str:
    """The tables of ``Docs/reports/p4_umons_quality.md`` as Markdown, one column per run; only numbers and ids."""
    labels = list(runs)
    out: list[str] = []

    def table(title: str, header: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        out.append(f"### {title}\n")
        out.append("| " + " | ".join(header) + " |")
        out.append("|" + "|".join("---" for _ in header) + "|")
        out.extend("| " + " | ".join(row) + " |" for row in rows)
        out.append("")

    def per_run(fn: Callable[[UmonsSummary], str]) -> list[str]:
        return [fn(runs[label]) for label in labels]

    scalar = [
        ("Files that ran / failed", lambda s: f"{s.files} / {len(s.errors)}"),
        ("Rows in the files", lambda s: f"{s.rows_in_file:,}"),
        ("Rows after repeated timestamps", lambda s: f"{s.rows:,}"),
        (
            "Repeated rows dropped / timestamps with two bodies",
            lambda s: f"{s.repeated_rows} / {s.ambiguous_timestamps}",
        ),
        ("Cells of the 17 joints at (0, 0, 0)", lambda s: f"{s.zero_joint_cells}"),
        ("Steps of dropped frames / pauses over 150 ms", lambda s: f"{s.steps_long:,} / {s.steps_pause:,}"),
        ("Largest step [s]", lambda s: f"{s.max_step_s:.3f}"),
        ("Grid rows (files resampled)", lambda s: f"{s.grid_rows:,} ({s.resampled_files})"),
        ("Mixed grid rows", lambda s: f"{s.mixed_rows:,} ({_pct(s.mixed_rows, s.grid_rows)})"),
        ("Usable frames", lambda s: _pct(s.usable_frames, s.grid_rows)),
        ("Not tracked frames", lambda s: f"{s.not_tracked_frames:,} ({_pct(s.not_tracked_frames, s.grid_rows, 3)})"),
        ("Cells, 26 joints: observed", lambda s: _pct(s.observed, s.cells)),
        ("Cells, 26 joints: bridged", lambda s: _pct(s.bridged, s.cells, 3)),
        ("Cells, 26 joints: missing", lambda s: _pct(s.missing, s.cells)),
        ("Cells, the 17 provided joints: observed", lambda s: _pct(s.provided_observed, s.provided_cells)),
        ("Cells, the 17 provided joints: bridged", lambda s: _pct(s.provided_bridged, s.provided_cells, 3)),
        ("Cells, the 17 provided joints: missing", lambda s: _pct(s.provided_missing, s.provided_cells, 3)),
        ("Filtered cells / usable cells not filtered", lambda s: f"{_pct(s.filtered, s.cells)} / {s.unfiltered:,}"),
        ("Swap cells suspect / blocked; warnings", lambda s: f"{s.suspect} / {s.blocked}; {s.swap_warnings}"),
        (
            "Bridged cells on the rows of the files, 17 joints (gap table)",
            lambda s: f"{s.gap_cells['filled']:,} ({_pct(s.gap_cells['filled'], s.rows * len(PROVIDED))})",
        ),
        (
            "Hampel cells of the 17 joints (rows of the files)",
            lambda s: f"{s.hampel_outliers:,} ({_pct(s.hampel_outliers, s.rows * len(PROVIDED))})",
        ),
        ("Seconds, chain and report", lambda s: f"{s.seconds:.1f}"),
    ]
    table("Run", ["Measure", *labels], [[name, *per_run(fn)] for name, fn in scalar])
    table(
        "Cells by reason: all cells whose reason is not ok (missing in brackets)",
        ["Reason", *labels],
        [
            [
                name,
                *[
                    f"{runs[label].unobserved_by_reason[name]:,} ({runs[label].missing_by_reason[name]:,})"
                    for label in labels
                ],
            ]
            for name in _REASONS
        ],
    )
    table(
        "Gaps of the rows of the files by outcome (cells inside the segment)",
        ["Outcome", *labels],
        [
            [name, *[f"{runs[label].gap_gaps[name]:,} ({runs[label].gap_cells[name]:,})" for label in labels]]
            for name in _OUTCOMES
        ],
    )

    def hampel_cell(summary: UmonsSummary, joint: str) -> str:
        n = summary.hampel_by_joint[joint]
        return f"{n:,} ({_pct(n, summary.rows)})"

    table(
        "Hampel: cells set to NaN, by joint of the 17 provided (share of the rows of the files)",
        ["Joint", *labels],
        [[JOINTS[j], *[hampel_cell(runs[label], JOINTS[j]) for label in labels]] for j in PROVIDED],
    )
    for label in labels:
        s = runs[label]
        table(
            f"Per file, {label}: min / p10 / median / max",
            ["Measure", "Value"],
            [
                ["Usable frames", _dist(s.usable_frames_share)],
                ["Usable cells of the 17 joints", _dist(s.provided_usable_share)],
                ["Mixed grid rows", _dist(s.mixed_share)],
                ["Hampel cells of the 17 joints", _dist(s.outlier_share)],
                ["Torso in the plane [mm]", _dist(s.torso_mm, 1.0, " mm", 0)],
                ["Step of the grid [ms]", _dist(s.step_ms, 1.0, " ms", 2)],
            ],
        )
        rows = [[key, _ids(value)] for key, value in s.notable.items()]
        table(f"Files worth naming, {label}", ["What", "Sequence ids"], rows)
        if s.errors:
            table(
                f"Files that failed, {label}",
                ["Sequence", "Error"],
                [[sid, msg.replace("|", "/")] for sid, msg in s.errors],
            )
    return "\n".join(out)


CSV_COLUMNS: Final = (
    "sequence_id", "rows_in_file", "rows", "repeated_rows", "ambiguous_timestamps", "zero_joint_cells", "duration_s",
    "steps_long", "steps_pause", "max_step_s", "grid_rows", "resampled", "mixed_rows", "step_ms", "torso_mm",
    "observed", "bridged", "missing", "provided_observed", "provided_bridged", "provided_missing", "usable_frames",
    "not_tracked_frames", "no_frame_cells", "hampel_outliers", "filtered", "unfiltered", "suspect", "blocked",
    "swap_warnings", "seconds", "error",
)  # fmt: skip


def _csv_row(r: SequenceResult) -> list[str]:
    """The cells of one row of ``CSV_COLUMNS``; every column is named, so a column cannot slip."""
    rep = r.report
    if rep is None:
        values = {"sequence_id": r.sequence_id, "error": r.error or ""}
        return [values.get(column, "") for column in CSV_COLUMNS]
    seg = rep.intervals[0]
    p_obs, p_br, p_mi = _provided(seg)
    torso, step = rep.timeline.torso_px, rep.timeline.step_s
    values = {
        "sequence_id": r.sequence_id,
        "rows_in_file": str(r.rows_in_file),
        "rows": str(seg.source_rows),
        "repeated_rows": str(r.repeated_rows),
        "ambiguous_timestamps": str(r.ambiguous_timestamps),
        "zero_joint_cells": str(r.zero_joint_cells),
        "duration_s": f"{r.duration_s:.3f}",
        "steps_long": str(r.steps_long),
        "steps_pause": str(r.steps_pause),
        "max_step_s": f"{r.max_step_s:.3f}",
        "grid_rows": str(seg.rows),
        "resampled": str(int(rep.timeline.resampled)),
        "mixed_rows": str(seg.mixed_rows),
        "step_ms": "" if step is None else f"{step * 1000:.4f}",
        "torso_mm": "" if torso is None else f"{torso:.1f}",
        "observed": str(seg.observed),
        "bridged": str(seg.bridged),
        "missing": str(seg.missing),
        "provided_observed": str(p_obs),
        "provided_bridged": str(p_br),
        "provided_missing": str(p_mi),
        "usable_frames": str(seg.usable_frames),
        "not_tracked_frames": str(seg.not_tracked_frames),
        "no_frame_cells": str(seg.missing_by_reason.no_frame),
        "hampel_outliers": str(sum(r.hampel_outliers)),
        "filtered": str(seg.filtered),
        "unfiltered": str(seg.unfiltered),
        "suspect": str(seg.suspect),
        "blocked": str(seg.blocked),
        "swap_warnings": str(sum(w.startswith("lr_swap_suspect@") for w in rep.warnings)),
        "seconds": f"{r.seconds:.3f}",
        "error": "",
    }
    return [values[column] for column in CSV_COLUMNS]


def write_per_file_csv(path: str | Path, results: Sequence[SequenceResult]) -> Path:
    """One row per file (counts only; an error row has the id and the message), written atomically."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for r in results:
        writer.writerow(_csv_row(r))
    return atomic_write_text(path, buffer.getvalue())
