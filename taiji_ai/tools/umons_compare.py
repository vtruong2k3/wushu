"""P6.07: the comparison chain checked on UMONS-TAICHI (D12): classes and segment boundaries, numbers and ids only.

Two sub-commands (``taiji_ai.bench.umons_compare`` has the rules; the dataset is CC BY-NC-SA 4.0, local, never in git,
and the numbers are **out of domain**: 13 basic techniques seen by a Kinect, not the 24 forms seen by a video pose):

* ``classes`` reads the segmented files (``Segmented_Kinect``): for every class and side a few references and queries
  (a seed chooses them) are aligned, a performer never with themself, and the tool reports whether the same class is
  closer and the nearest-reference class.
* ``boundaries`` reads the continuous recordings (``Kinect``) and their labels (``Labels``): pairs of two performers of
  one capture with equal label sequences are aligned, the label boundaries of the reference are carried to the query
  through the warping path and compared with the query's own labels (temporal IoU, errors in seconds), next to a
  uniform-scaling reference line.

``--umons`` is the dataset root, its ``extracted`` folder or the folder of the files. The run settings are arguments
with the plan's defaults and are echoed in every output (``--min-visible`` defaults to half the units rounded up,
``--band`` to 0.2 for ``classes`` and 0.1 for ``boundaries``, ``--step`` to ``symmetricP1``; weights are 1 and the
quality chain runs with its defaults); nothing is tuned on these files. ``--seed`` (default 1) chooses the sample,
``--max-pairs`` caps the pairs (``boundaries`` default 40; ``classes`` default: all). ``--out`` receives CSV files
(ignored by git): ``classes``: ``pairs.csv``, ``classes.csv``, ``selection.csv``; ``boundaries``: ``pairs.csv``,
``parts.csv``. With ``--report FILE`` the Markdown tables are written there. Only dataset ids (``P01T01C03``,
``P01T01C03G05D01S02``) and numbers are printed or written: no path, no value of a skeleton, no time of a label.

Usage (from ``taiji_ai/``)::

    python tools/umons_compare.py classes --umons ../datasets/taiji/umons --out data/reports/p6_07/classes
    python tools/umons_compare.py boundaries --umons ../datasets/taiji/umons --out data/reports/p6_07/boundaries

Exit codes: 0 every file and pair ran, 1 the run finished and at least one file or pair failed (listed by id), 2 the run
could not start (a folder that is not the dataset, a bad option, nothing to run).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from taiji_ai.bench import BenchError
from taiji_ai.bench.umons import find_umons, load_kinect
from taiji_ai.bench.umons_compare import (
    DEFAULT_BAND_BOUNDARIES,
    DEFAULT_BAND_CLASSES,
    DEFAULT_BOUNDARY_PAIRS,
    DEFAULT_QUERIES,
    DEFAULT_REFERENCES,
    DEFAULT_STEP,
    BoundaryExperiment,
    ClassExperiment,
    LabelRow,
    SequenceId,
    UmonsCompareError,
    boundaries_csv,
    boundary_experiment,
    boundary_parts_csv,
    check_seed,
    class_pairs_csv,
    class_selection_csv,
    class_table_csv,
    classes_experiment,
    features_loader,
    find_folder,
    list_labels,
    list_segments,
    list_sequences,
    load_labels,
    load_segment,
    make_settings,
    render_boundaries,
    render_classes,
    settings_line,
)
from taiji_ai.logs import configure_logging
from taiji_ai.store.artifacts import atomic_write_text

MAX_LISTED = 10  # failed files and pairs printed (all of them are in the report)


def _integer(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer") from None


def _number(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a number") from None


def _name(text: str) -> str:
    return text  # checked by ``make_settings`` (its message never echoes the value)


class _Parser(argparse.ArgumentParser):
    """An ``ArgumentParser`` whose errors never repeat a string of the command line (an unknown option or command)."""

    def error(self, message: str):  # type: ignore[no-untyped-def]
        if any(mark in message for mark in ("invalid choice", "unrecognized", "ambiguous")):
            message = "an option or a command is not known (see --help)"
        self.print_usage(sys.stderr)
        sys.stderr.write(f"error: {message}\n")
        raise SystemExit(2)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    classes = sub.add_parser("classes", help="is the same class closer? (segmented files)")
    boundaries = sub.add_parser("boundaries", help="segment boundaries carried through the warping path")
    defaults = ((classes, DEFAULT_BAND_CLASSES, None), (boundaries, DEFAULT_BAND_BOUNDARIES, DEFAULT_BOUNDARY_PAIRS))
    for p, band, pairs in defaults:
        p.add_argument("--umons", required=True, type=Path, help="the dataset root, its extracted folder or a folder")
        p.add_argument("--out", required=True, type=Path, help="folder for the CSV files (ignored by git)")
        p.add_argument("--report", type=Path, default=None, help="write the Markdown tables to this file")
        p.add_argument("--seed", type=_integer, default=1, help="seed of the sample (default 1)")
        p.add_argument("--max-pairs", type=_integer, default=pairs, help="at most this many pairs (seeded subset)")
        p.add_argument("--min-visible", type=_integer, default=None, help="units valid in both frames (default: half)")
        p.add_argument("--band", type=_number, default=band, help=f"band in (0, 1] (default {band:g})")
        p.add_argument("--step", type=_name, default=DEFAULT_STEP, help=f"step pattern (default {DEFAULT_STEP})")
    classes.add_argument("--references", type=_integer, default=DEFAULT_REFERENCES, help="references per class, side")
    classes.add_argument("--queries", type=_integer, default=DEFAULT_QUERIES, help="queries per class and side")
    return parser


def _progress(label: str):
    state = {"last": -1}

    def report(done: int, total: int) -> None:
        step = max(1, total // 10)
        if done == total or done % step == 0:
            if state["last"] != done:
                state["last"] = done
                sys.stderr.write(f"{label}: {done}/{total} pairs\n")

    return report


def _listed(items: Sequence[str], total: int) -> list[str]:
    lines = [f"  failed {item}" for item in items[:MAX_LISTED]]
    if total > MAX_LISTED:
        lines.append(f"  ... and {total - MAX_LISTED} more (see the report)")
    return lines


def _share(part: int, whole: int) -> str:
    return f"{100.0 * part / whole:.1f} %" if whole else "n/a"


def _classes_lines(exp: ClassExperiment, seconds: float) -> list[str]:
    s, run = exp.summary, exp.run
    lines = [
        settings_line(exp.settings, exp.seed),
        f"classes: pairs aligned {len(run.distances)} of {exp.available_pairs} available, same-performer pairs "
        f"left out {exp.same_performer_skipped}, no path {s.pairs_no_path}, segments failed "
        f"{len(run.failed_segments)}, pairs refused {len(run.failed_pairs)}, {seconds:.1f} s",
        f"classes: the own class is closer in {s.classes_own_closer} of {s.classes_compared} "
        f"({_share(s.classes_own_closer, s.classes_compared)}); nearest reference of the same class for "
        f"{s.nn_correct} of {s.nn_queries} queries ({_share(s.nn_correct, s.nn_queries)})",
    ]
    for side, summary in exp.by_side.items():
        lines.append(
            f"classes side D{side:02d}: own closer {summary.classes_own_closer} of {summary.classes_compared}, "
            f"nearest correct {summary.nn_correct} of {summary.nn_queries}"
        )
    items = [f"{i}: {e}" for i, e in run.failed_segments] + [f"{q}/{r}: {e}" for q, r, e in run.failed_pairs]
    return lines + _listed(items, len(items))


def _run_classes(args: argparse.Namespace) -> int:
    settings = make_settings(band=args.band, min_visible=args.min_visible, step=args.step)
    seed = check_seed(args.seed)
    files = list_segments(find_folder(args.umons, "Segmented_Kinect"))
    if not files:
        raise UmonsCompareError("the Segmented_Kinect folder holds no segmented file")
    loader = features_loader({s.text: path for s, path in files.items()}, load_segment)
    started = time.perf_counter()
    exp = classes_experiment(
        files, loader, settings=settings, seed=seed, references=args.references, queries=args.queries,
        max_pairs=args.max_pairs, progress=_progress("classes"),
    )  # fmt: skip
    if exp.planned_pairs == 0:
        raise UmonsCompareError("no pair to align: no class has a reference and a query of two performers on one side")
    args.out.mkdir(parents=True, exist_ok=True)
    atomic_write_text(args.out / "pairs.csv", class_pairs_csv(exp))
    atomic_write_text(args.out / "classes.csv", class_table_csv(exp))
    atomic_write_text(args.out / "selection.csv", class_selection_csv(exp))
    if args.report is not None:
        atomic_write_text(args.report, render_classes(exp))
    sys.stdout.write("\n".join(_classes_lines(exp, time.perf_counter() - started)) + "\n")
    return 1 if exp.run.failed_segments or exp.run.failed_pairs else 0


def _boundary_lines(exp: BoundaryExperiment, failed_labels: Sequence[tuple[str, str]], seconds: float) -> list[str]:
    s, run, c = exp.summary, exp.run, exp.candidates
    lines = [
        settings_line(exp.settings, exp.seed),
        f"boundaries: pairs usable {len(c.usable)}, different labels left out {c.different_labels}, aligned "
        f"{len(run.pairs)}, no path {s.pairs_no_path}, recordings failed {len(run.failed_sequences)}, pairs refused "
        f"{len(run.failed_pairs)}, label files failed {len(failed_labels)}, {seconds:.1f} s",
        f"boundaries: parts measured {s.parts}, no end {s.parts_open}, outside the reference clock {s.parts_outside}",
    ]
    for family in ("all", "ex", "tech"):
        for method, stats in (("warping", s.stats[family]), ("uniform", s.uniform[family])):
            median = "n/a" if stats.iou_median is None else f"{stats.iou_median:.3f}"
            start = "n/a" if stats.start_abs_median is None else f"{stats.start_abs_median:.3f}"
            end = "n/a" if stats.end_abs_median is None else f"{stats.end_abs_median:.3f}"
            lines.append(
                f"boundaries {family} {method}: parts {stats.n}, IoU median {median}, "
                f"start error median {start} s, end error median {end} s"
            )
    items = (
        [f"{i}: {e}" for i, e in failed_labels]
        + [f"{i}: {e}" for i, e in run.failed_sequences]
        + [f"{r}/{q}: {e}" for r, q, e in run.failed_pairs]
    )
    return lines + _listed(items, len(items))


def _run_boundaries(args: argparse.Namespace) -> int:
    settings = make_settings(band=args.band, min_visible=args.min_visible, step=args.step)
    seed = check_seed(args.seed)
    sequences = list_sequences(find_umons(args.umons))
    label_files = list_labels(find_folder(args.umons, "Labels"))
    labels: dict[SequenceId, tuple[LabelRow, ...]] = {}
    failed_labels: list[tuple[str, str]] = []
    for sequence, path in label_files.items():
        try:
            labels[sequence] = load_labels(path)
        except UmonsCompareError as exc:
            failed_labels.append((sequence.text, str(exc)))
    loader = features_loader({q.text: path for q, path in sequences.items()}, load_kinect)
    started = time.perf_counter()
    exp = boundary_experiment(
        labels, set(sequences), loader, settings=settings, seed=seed, max_pairs=args.max_pairs,
        progress=_progress("boundaries"),
    )  # fmt: skip
    if not exp.candidates.usable:
        raise UmonsCompareError("no pair to align: no two performers of one capture have equal label sequences")
    args.out.mkdir(parents=True, exist_ok=True)
    atomic_write_text(args.out / "pairs.csv", boundaries_csv(exp))
    atomic_write_text(args.out / "parts.csv", boundary_parts_csv(exp))
    if args.report is not None:
        extra = ""
        if failed_labels:
            rows = "\n".join(f"| {i} | {e.replace('|', '/')} |" for i, e in failed_labels)
            extra = f"\n### Label files that failed\n\n| Id | Error |\n|---|---|\n{rows}\n"
        atomic_write_text(args.report, render_boundaries(exp) + extra)
    sys.stdout.write("\n".join(_boundary_lines(exp, failed_labels, time.perf_counter() - started)) + "\n")
    failed = failed_labels or exp.run.failed_sequences or exp.run.failed_pairs
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    configure_logging(level="WARNING")
    try:
        return _run_classes(args) if args.command == "classes" else _run_boundaries(args)
    except BenchError as exc:  # UmonsCompareError and UmonsError are BenchErrors: no message names a path
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
