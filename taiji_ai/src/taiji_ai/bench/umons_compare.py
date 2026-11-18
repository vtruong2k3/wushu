"""P6.07: the comparison chain checked on UMONS-TAICHI (D12), two experiments, numbers and ids only.

**Third-party data, internal development only, out of domain.** UMONS-TAICHI is CC BY-NC-SA 4.0 and tagged
``dev-test`` and ``benchmark`` in ``Docs/DATASET_REGISTRY_TAIJI.md``; it is 13 basic techniques seen by a Kinect, not
the 24 forms seen by a video pose, so nothing here is a product number (AGENTS.md 9.4.4). This module lives in
``bench/`` and no product code imports it. Only counts, shares, medians and the dataset's own ids (``P01T01C03``,
``P01T01C03G05D01S02``) leave it; no value of a skeleton and no time of a label is stored or printed. **Nothing is
tuned here**: ``min_visible``, the band, the step and the quality chain are inputs (``AlignSettings``), echoed in
every table and CSV.

**The ids.** A continuous recording is ``PxxTxxCxx`` (performer, trial, capture) and a segmented file is
``PxxTxxCxxGxxDxxSxx`` (the same, then class, side, repetition). The meaning of G, D and S is **inferred** by the
dataset notes (``datasets/taiji/README.md``: 13 classes, left or right, repetition), not documented by the authors;
here G is read as the class, D as the side (a pair is aligned only inside one side) and S as the repetition.

**Experiment 1, classes.** For every class and side a few *reference* segments and *query* segments are chosen with a
seed (``select_segments``: one segment per performer before a second of the same one, the order of the candidates
given by a hash of the seed and the id, so a choice never depends on a random-number library). Every query is aligned
(``compare.align.align``: features, masked cost, constrained DTW) with every reference **of the same side and of
another performer**: a performer is never compared with themself (``plan_pairs``, and ``summarise_classes`` refuses
such a pair). Per class: the median distance ``D`` to the references of its own class and to the others, whether the
own is smaller, and the share of classes where it is; second, the nearest-reference class of every query (1-NN; a tie
goes to the lower class). A pair with no path (``status="no_path"``: for ``symmetricP1`` lengths more than 2 to 1) is
a result: it is left out of the medians and counted, own and other apart.

**Experiment 2, boundaries.** Pairs of continuous recordings of one capture and two performers whose label sequences
(``.lab``, rests included) are equal; the whole recordings are aligned; the boundaries of each labelled part of the
reference are carried to the query through ``Alignment.matched_query_times()`` (the mean query time along the path for
every reference row, linear between rows; a boundary outside the reference clock is left out and counted, never
clamped) and compared with the query's own part of the same rank: temporal IoU and the error of the start and of the
end in seconds. A part is the interval between two onsets; ``_`` (rest) parts count for the equality of the sequences
but are not measured; the last part of a file has no end and is left out and counted. A reference line is computed
from the same pairs: **uniform scaling** of the clock (the span of the reference mapped linearly to the span of the
query, no warping).

``.lab`` rule: one ``time label`` per line (seconds, strictly increasing), ``_`` or ``ex`` / ``tech`` + digits + an
optional ``l`` or ``r``; a line that is not that is refused with its number. Errors name an id and a line, never a
path, a label or a free text of the caller.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import math
import re
import time
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np

from taiji_ai.bench import BenchError
from taiji_ai.bench.umons import KinectSequence, UmonsError, parse_kinect
from taiji_ai.compare import CompareError
from taiji_ai.compare.align import Alignment, align
from taiji_ai.compare.dtw import STEPS
from taiji_ai.compare.features import DEFAULT_JOINTS, DEFAULT_SEGMENTS, FrameFeatures, frame_features
from taiji_ai.quality import QualityError
from taiji_ai.quality.chain import QualityParams, run_quality_arrays
from taiji_ai.quality.layers_io import QualityLayerError, pose_filtered_from_result
from taiji_ai.schemas.quality_layers import DataSource

log = logging.getLogger(__name__)

N_UNITS: Final = len(DEFAULT_JOINTS) + len(DEFAULT_SEGMENTS)  # 12 positions and 9 angles
DEFAULT_REFERENCES: Final = 3  # references per class and side (plan Q2)
DEFAULT_QUERIES: Final = 5  # queries per class and side (plan Q2)
DEFAULT_BOUNDARY_PAIRS: Final = 40  # sequence pairs for the boundaries (plan Q2)
DEFAULT_BAND_CLASSES: Final = 0.2  # segments (plan Q3)
DEFAULT_BAND_BOUNDARIES: Final = 0.1  # whole sequences (plan Q3)
DEFAULT_STEP: Final = "symmetricP1"
FAMILIES: Final = ("ex", "tech")  # the families of labelled parts that are measured
RECORDING_ID: Final = "3d8f6a52-9c41-4b07-a1e6-5f2c7d90b384"  # the layers need one: a fixed id for every file
SOURCES: Final = (DataSource(dataset_id="D12", license="CC BY-NC-SA 4.0"),)
FOLDERS: Final = ("Kinect", "Segmented_Kinect", "Labels")
MAX_SEED: Final = 2**32

_SEQUENCE: Final = re.compile(r"P([0-9]{2})T([0-9]{2})C([0-9]{2})")
_SEGMENT: Final = re.compile(r"P([0-9]{2})T([0-9]{2})C([0-9]{2})G([0-9]{2})D([0-9]{2})S([0-9]{2})")
_LINE_BREAK: Final = re.compile(r"\r\n|\r|\n")
_TIME: Final = re.compile(r"(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_LABEL: Final = re.compile(r"_|(?:ex|tech)[0-9]+[lr]?")
_LICENSE_FILE: Final = "License.txt"
_LICENSE_MARK: Final = "CC BY-NC-SA"


class UmonsCompareError(BenchError):
    """An input of the UMONS check is wrong (an id, a label file, a setting, a folder); the message names an id and a
    line, never a path, a label or a string given by the caller."""


# the errors of a file that cannot be used (a data problem to report by id), as opposed to a bug, which propagates
FEATURE_ERRORS: Final = (UmonsError, UmonsCompareError, QualityError, QualityLayerError, CompareError)


# --- the ids ---------------------------------------------------------------------------------------------------------
@dataclass(frozen=True, order=True)
class SequenceId:
    """A continuous recording ``PxxTxxCxx``: performer, trial, capture (integers read from the two digits)."""

    performer: int
    trial: int
    capture: int

    @property
    def text(self) -> str:
        return f"P{self.performer:02d}T{self.trial:02d}C{self.capture:02d}"


@dataclass(frozen=True, order=True)
class SegmentId:
    """A segmented file ``PxxTxxCxxGxxDxxSxx``: its recording, then class, side, repetition (the dataset notes' reading
    of G, D, S; an inference, not documented by the authors)."""

    sequence: SequenceId
    klass: int
    side: int
    repetition: int

    @property
    def performer(self) -> int:
        return self.sequence.performer

    @property
    def text(self) -> str:
        return f"{self.sequence.text}G{self.klass:02d}D{self.side:02d}S{self.repetition:02d}"


def parse_sequence_id(name: object) -> SequenceId:
    """``PxxTxxCxx`` (two ASCII digits each) as a ``SequenceId``; ``UmonsCompareError`` for any other value."""
    found = _SEQUENCE.fullmatch(name) if isinstance(name, str) else None
    if found is None:
        raise UmonsCompareError("not a dataset sequence id (expected the form P01T01C03)")
    performer, trial, capture = (int(g) for g in found.groups())
    return SequenceId(performer, trial, capture)


def parse_segment_id(name: object) -> SegmentId:
    """``PxxTxxCxxGxxDxxSxx`` (two ASCII digits each) as a ``SegmentId``; ``UmonsCompareError`` for any other value."""
    found = _SEGMENT.fullmatch(name) if isinstance(name, str) else None
    if found is None:
        raise UmonsCompareError("not a dataset segment id (expected the form P01T01C03G05D01S02)")
    performer, trial, capture, klass, side, repetition = (int(g) for g in found.groups())
    return SegmentId(SequenceId(performer, trial, capture), klass, side, repetition)


# --- the labels ------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class LabelRow:
    """One line of a ``.lab`` file: the onset ``t_sec`` (seconds from the first Kinect row, as the files are read) and
    the label that starts there."""

    t_sec: float
    label: str


@dataclass(frozen=True)
class LabelPart:
    """The interval ``[start_s, end_s)`` of a label (seconds); ``end_s`` is ``None`` for the last onset (no later onset
    says where it ends); ``family`` is ``rest``, ``ex`` or ``tech``."""

    label: str
    family: str
    start_s: float
    end_s: float | None


def parse_labels(text: str, sequence_id: str) -> tuple[LabelRow, ...]:
    """The rows of a ``.lab`` text: ``time label`` per line, time strictly increasing, any line ending (LF, CRLF, CR),
    blank lines allowed. ``UmonsCompareError`` naming the sequence and the physical line (blank lines counted) for a
    line that is not a time and a label, a time that is not finite or does not increase, a label of no known kind, or
    a text with no row. The message never repeats the line."""
    sid = parse_sequence_id(sequence_id).text
    rows: list[LabelRow] = []
    previous: float | None = None
    for number, raw in enumerate(_LINE_BREAK.split(text), start=1):
        if not raw.strip():
            continue
        tokens = raw.split()
        if len(tokens) != 2:
            raise UmonsCompareError(f"{sid}: line {number}: expected a time and a label")
        time_token, label = tokens
        if _TIME.fullmatch(time_token) is None:
            raise UmonsCompareError(f"{sid}: line {number}: the time is not a number of seconds")
        t = float(time_token)
        if not math.isfinite(t):
            raise UmonsCompareError(f"{sid}: line {number}: the time is not finite")
        if _LABEL.fullmatch(label) is None:
            raise UmonsCompareError(f"{sid}: line {number}: the label is not _, exN or techN with an optional l or r")
        if previous is not None and t <= previous:
            raise UmonsCompareError(f"{sid}: line {number}: the time does not increase")
        rows.append(LabelRow(t, label))
        previous = t
    if not rows:
        raise UmonsCompareError(f"{sid}: the file has no rows")
    return tuple(rows)


def load_labels(path: str | Path) -> tuple[LabelRow, ...]:
    """Read a ``.lab`` file; its sequence id is the file stem. ``FileNotFoundError``, ``UmonsCompareError``."""
    file = Path(path)
    sid = parse_sequence_id(file.stem).text
    try:
        text = file.read_bytes().decode("ascii")  # bytes: the line endings reach the parser as they are
    except UnicodeDecodeError:
        raise UmonsCompareError(f"{sid}: the file is not ASCII text") from None
    return parse_labels(text, sid)


def label_family(label: str) -> str:
    """``rest`` for ``_``, ``ex`` or ``tech`` for those labels; ``UmonsCompareError`` for anything else."""
    if not isinstance(label, str) or _LABEL.fullmatch(label) is None:
        raise UmonsCompareError("the label is not _, exN or techN with an optional l or r")
    if label == "_":
        return "rest"
    return "ex" if label.startswith("ex") else "tech"


def label_parts(rows: Sequence[LabelRow]) -> tuple[LabelPart, ...]:
    """One part per onset: it ends at the next onset; the last has no end (``None``)."""
    parts = []
    for i, row in enumerate(rows):
        end = rows[i + 1].t_sec if i + 1 < len(rows) else None
        parts.append(LabelPart(row.label, label_family(row.label), row.t_sec, end))
    return tuple(parts)


# --- the settings and the seeded choice ------------------------------------------------------------------------------
@dataclass(frozen=True)
class AlignSettings:
    """The settings of ``align`` for a run: ``min_visible`` (units valid in both frames), ``band`` (a fraction of the
    length) and ``step``; weights are 1 for every unit and the features' two minimums are not applied. They are inputs,
    never tuned on these files."""

    min_visible: int
    band: float
    step: str


def _number(value: object) -> float | None:
    """``value`` as a finite float, or ``None`` (a bool, a non-number, an infinity, an integer beyond the float
    range)."""
    if isinstance(value, bool) or not isinstance(value, int | float | np.integer | np.floating):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | np.integer):
        return None
    return int(value)


def make_settings(*, band: object, min_visible: object = None, step: object = DEFAULT_STEP) -> AlignSettings:
    """Validated settings: ``band`` a number in (0, 1]; ``min_visible`` an integer from 1 to the number of units,
    ``None`` meaning half of them rounded up (11 of 21); ``step`` one of ``compare.dtw.STEPS``. ``UmonsCompareError``,
    which never echoes the value."""
    width = _number(band)
    if width is None or not 0.0 < width <= 1.0:
        raise UmonsCompareError("band must be a number in (0, 1]")
    if min_visible is None:
        visible = math.ceil(N_UNITS / 2)
    else:
        given = _integer(min_visible)
        if given is None or not 1 <= given <= N_UNITS:
            raise UmonsCompareError(f"min_visible must be an integer from 1 to {N_UNITS}")
        visible = given
    if not isinstance(step, str) or step not in STEPS:
        raise UmonsCompareError(f"step must be one of {', '.join(STEPS)}")
    return AlignSettings(min_visible=visible, band=width, step=step)


def check_seed(seed: object) -> int:
    """The seed as an ``int`` in ``[0, 2**32)``; ``UmonsCompareError`` otherwise."""
    value = _integer(seed)
    if value is None or not 0 <= value < MAX_SEED:
        raise UmonsCompareError("seed must be an integer from 0 to 2**32 - 1")
    return value


def _positive(value: object, name: str) -> int:
    given = _integer(value)
    if given is None or given < 1:
        raise UmonsCompareError(f"{name} must be an integer of at least 1")
    return given


def _rank(seed: int, *parts: object) -> int:
    """A number that orders candidates: the SHA-256 of the seed and the parts, so the choice is the same on every
    platform and version (no random-number library)."""
    key = "|".join(str(p) for p in (seed, *parts))
    return int.from_bytes(hashlib.sha256(key.encode("ascii")).digest()[:8], "big")


Group = tuple[int, int]  # (class, side)


def select_segments(
    segments: Iterable[SegmentId], *, per_group: int, seed: int, exclude: Collection[SegmentId] = ()
) -> dict[Group, tuple[SegmentId, ...]]:
    """Up to ``per_group`` segments of every ``(class, side)``, none of ``exclude``: one segment per performer before a
    second of the same performer (performers and segments ordered by a hash of ``seed`` and the id), each group sorted.
    A group with fewer segments gives all of them; a group with none is absent. ``UmonsCompareError`` for a bad count or
    seed."""
    count, key = _positive(per_group, "per_group"), check_seed(seed)
    excluded = set(exclude)
    groups: dict[Group, dict[int, list[SegmentId]]] = {}
    for item in set(segments):
        if item not in excluded:
            groups.setdefault((item.klass, item.side), {}).setdefault(item.performer, []).append(item)
    chosen: dict[Group, tuple[SegmentId, ...]] = {}
    for group in sorted(groups):
        by_performer = groups[group]
        order = sorted(by_performer, key=lambda p: (_rank(key, "performer", *group, p), p))
        queues = [sorted(by_performer[p], key=lambda s: (_rank(key, "segment", s.text), s.text)) for p in order]
        picked: list[SegmentId] = []
        depth = 0
        while len(picked) < count and any(depth < len(q) for q in queues):
            for queue in queues:
                if depth < len(queue) and len(picked) < count:
                    picked.append(queue[depth])
            depth += 1
        chosen[group] = tuple(sorted(picked))
    return chosen


@dataclass(frozen=True)
class PairPlan:
    """The pairs ``(query, reference)`` to align and how many were left out because both are one performer's."""

    pairs: tuple[tuple[SegmentId, SegmentId], ...]
    skipped_same_performer: int


def plan_pairs(
    references: Mapping[Group, Sequence[SegmentId]], queries: Mapping[Group, Sequence[SegmentId]]
) -> PairPlan:
    """Every query with every reference of the **same side**, except a reference of the query's own performer (a
    performer is never compared with themself); sorted by ``(query, reference)``. A query with no reference on its side
    gives no pair and is not counted as skipped."""
    by_side: dict[int, list[SegmentId]] = {}
    for group in references.values():
        for reference in group:
            by_side.setdefault(reference.side, []).append(reference)
    pairs: list[tuple[SegmentId, SegmentId]] = []
    skipped = 0
    for query in sorted(q for group in queries.values() for q in group):
        for reference in sorted(by_side.get(query.side, ())):
            if reference.performer == query.performer:
                skipped += 1
                continue
            pairs.append((query, reference))
    return PairPlan(tuple(pairs), skipped)


def cap_pairs[P: tuple[SegmentId | SequenceId, SegmentId | SequenceId]](
    pairs: Sequence[P], max_pairs: int | None, seed: int
) -> tuple[P, ...]:
    """At most ``max_pairs`` of ``pairs`` (``None``: all), chosen by the hash of the seed and the two ids, in the
    original order. ``UmonsCompareError`` for a bad limit or seed."""
    key = check_seed(seed)
    if max_pairs is None:
        return tuple(pairs)
    limit = _positive(max_pairs, "max_pairs")
    if limit >= len(pairs):
        return tuple(pairs)
    ranked = sorted(pairs, key=lambda p: (_rank(key, "pair", p[0].text, p[1].text), p[0].text, p[1].text))
    kept = set(ranked[:limit])
    return tuple(p for p in pairs if p in kept)


# --- the features of a file ------------------------------------------------------------------------------------------
def features_of(sequence: KinectSequence, quality: QualityParams | None = None) -> FrameFeatures:
    """The quality chain (defaults unless ``quality``) over a Kinect sequence, then the frame features of P6.01 (default
    joints and segments, no roll, no minimum length). The clock is the file's own, from its first row, on the chain's
    grid. Raises the chain's and the features' errors (see ``FEATURE_ERRORS``)."""
    result = run_quality_arrays(
        sequence.keypoints, sequence.scores, sequence.t_sec, tracked=sequence.tracked, params=quality
    )
    layer = pose_filtered_from_result(
        result,
        recording_id=RECORDING_ID,
        frame_index=np.arange(len(sequence.t_sec), dtype=np.int64),
        data_sources=SOURCES,
    )
    return frame_features(layer)


def load_segment(path: str | Path) -> KinectSequence:
    """Read a segmented Kinect file (its id is the file stem) through ``bench.umons.parse_kinect``, which accepts a
    sequence id only: the segment is parsed under its parent sequence id. ``FileNotFoundError``,
    ``UmonsCompareError`` naming the segment (never the path)."""
    file = Path(path)
    segment = parse_segment_id(file.stem)
    try:
        text = file.read_bytes().decode("ascii")
    except UnicodeDecodeError:
        raise UmonsCompareError(f"{segment.text}: the file is not ASCII text") from None
    try:
        return parse_kinect(text, segment.sequence.text)
    except UmonsError as exc:
        raise UmonsCompareError(f"{segment.text}: {exc}") from exc


def features_loader(
    files: Mapping[str, Path], read: Callable[[Path], KinectSequence], quality: QualityParams | None = None
) -> Callable[[str], FrameFeatures]:
    """A function from an id text to its features: ``read`` the file of ``files[id]`` and run ``features_of``."""

    def load(key: str) -> FrameFeatures:
        return features_of(read(files[key]), quality)

    return load


class _FeatureCache:
    """Features by id, each computed once; a file that fails with a known error is remembered as failed."""

    def __init__(self, loader: Callable[[str], FrameFeatures]) -> None:
        self._loader = loader
        self._features: dict[str, FrameFeatures | None] = {}
        self.failed: dict[str, str] = {}

    def get(self, key: str) -> FrameFeatures | None:
        if key not in self._features:
            try:
                self._features[key] = self._loader(key)
            except FEATURE_ERRORS as exc:
                self._features[key] = None
                self.failed[key] = f"{type(exc).__name__}: {exc}"
                log.warning("features failed for %s: %s", key, type(exc).__name__)
        return self._features[key]


# --- the folders -----------------------------------------------------------------------------------------------------
def find_folder(root: str | Path, name: str) -> Path:
    """The folder ``name`` (``Kinect``, ``Segmented_Kinect`` or ``Labels``) of the dataset: ``root/name``,
    ``root/extracted/name`` or ``root`` itself when it is called ``name``. It must hold ``License.txt`` naming CC
    BY-NC-SA. ``UmonsCompareError`` (no message names a path)."""
    if name not in FOLDERS:
        raise UmonsCompareError(f"the folder must be one of {', '.join(FOLDERS)}")
    base = Path(root)
    if not base.is_dir():
        raise UmonsCompareError("the UMONS folder does not exist")
    for candidate in (base / name, base / "extracted" / name, base if base.name == name else None):
        if candidate is not None and candidate.is_dir():
            folder = candidate
            break
    else:
        raise UmonsCompareError(f"no {name} folder found under the UMONS folder")
    license_file = folder / _LICENSE_FILE
    if not license_file.is_file():
        raise UmonsCompareError(f"{_LICENSE_FILE} is missing in the {name} folder")
    if _LICENSE_MARK not in license_file.read_text(encoding="utf-8", errors="replace"):
        raise UmonsCompareError(f"{_LICENSE_FILE} in the {name} folder does not name {_LICENSE_MARK} 4.0")
    return folder


def _entries(folder: Path, suffix: str, parse: Callable[[str], object], what: str) -> dict:
    found: dict = {}
    for entry in sorted(folder.iterdir()):
        if entry.name == _LICENSE_FILE:
            continue
        if not entry.is_file() or entry.suffix != suffix:
            raise UmonsCompareError(f"a folder entry is not a {what}")
        try:
            found[parse(entry.stem)] = entry
        except UmonsCompareError:
            raise UmonsCompareError(f"a folder entry is not a {what}") from None
    return dict(sorted(found.items()))


def list_segments(folder: str | Path) -> dict[SegmentId, Path]:
    """``{id: file}`` of the segmented files of a folder, sorted by id (``License.txt`` is skipped; any other entry that
    is not ``PxxTxxCxxGxxDxxSxx.txt`` is refused without naming it)."""
    return _entries(Path(folder), ".txt", parse_segment_id, "segmented file PxxTxxCxxGxxDxxSxx.txt")


def list_sequences(folder: str | Path) -> dict[SequenceId, Path]:
    """``{id: file}`` of the continuous recordings of a folder (``PxxTxxCxx.txt``), sorted by id."""
    return _entries(Path(folder), ".txt", parse_sequence_id, "recording PxxTxxCxx.txt")


def list_labels(folder: str | Path) -> dict[SequenceId, Path]:
    """``{id: file}`` of the ``.lab`` files of a folder (``PxxTxxCxx.lab``), sorted by id."""
    return _entries(Path(folder), ".lab", parse_sequence_id, "label file PxxTxxCxx.lab")


# --- experiment 1: the classes ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class PairDistance:
    """``D`` of one query aligned with one reference (dimensionless), or ``None`` when the pair has no path."""

    query: SegmentId
    reference: SegmentId
    distance: float | None

    @property
    def status(self) -> str:
        return "no_path" if self.distance is None else "ok"


@dataclass(frozen=True)
class ClassRun:
    """The alignments of a list of pairs: the distances, the segments whose features failed (id, error), the pairs
    whose alignment was refused (query, reference, error), how many pairs were skipped for a failed segment, and the
    seconds."""

    distances: tuple[PairDistance, ...]
    failed_segments: tuple[tuple[str, str], ...]
    failed_pairs: tuple[tuple[str, str, str], ...]
    skipped_pairs: int
    seconds: float


Progress = Callable[[int, int], None]


def run_classes(
    pairs: Sequence[tuple[SegmentId, SegmentId]],
    features_for: Callable[[str], FrameFeatures],
    settings: AlignSettings,
    progress: Progress | None = None,
) -> ClassRun:
    """Align each ``(query, reference)`` with ``settings``. ``features_for(id_text)`` is called once per segment; a
    segment that fails with a known error (``FEATURE_ERRORS``) is listed and its pairs skipped; a pair that ``align``
    refuses is listed; any other error is a bug and propagates. ``progress(done, total)`` is called after every pair."""
    started = time.perf_counter()
    cache = _FeatureCache(features_for)
    distances: list[PairDistance] = []
    failed_pairs: list[tuple[str, str, str]] = []
    skipped = 0
    for done, (query, reference) in enumerate(pairs, start=1):
        reference_features, query_features = cache.get(reference.text), cache.get(query.text)
        if reference_features is None or query_features is None:
            skipped += 1
        else:
            try:
                alignment = align(
                    reference_features,
                    query_features,
                    min_visible=settings.min_visible,
                    band=settings.band,
                    step=settings.step,
                )
            except CompareError as exc:
                failed_pairs.append((query.text, reference.text, f"{type(exc).__name__}: {exc}"))
            else:
                distances.append(PairDistance(query, reference, alignment.distance))
        if progress is not None:
            progress(done, len(pairs))
    return ClassRun(
        tuple(distances), tuple(cache.failed.items()), tuple(failed_pairs), skipped, time.perf_counter() - started
    )


@dataclass(frozen=True)
class ClassRow:
    """One class (of the queries) over the pairs given: ``queries`` distinct queries with a pair, ``own_*`` the pairs
    with references of the same class and ``other_*`` of the others (``*_pairs`` with a distance, ``*_no_path``
    without), ``own_median`` and ``other_median`` of ``D`` (``None`` for no pair), ``own_closer`` whether the own
    median is strictly smaller (``None`` when either is missing), ``nn_queries`` the queries with a distance and
    ``nn_correct`` those whose nearest reference is of their class."""

    klass: int
    queries: int
    own_pairs: int
    other_pairs: int
    own_no_path: int
    other_no_path: int
    own_median: float | None
    other_median: float | None
    own_closer: bool | None
    nn_queries: int
    nn_correct: int


@dataclass(frozen=True)
class ClassSummary:
    """The rows by class and the totals: classes compared, classes where the own class is closer and their share,
    queries and nearest-class results, and the pairs with a distance and without a path."""

    rows: tuple[ClassRow, ...]
    classes_compared: int
    classes_own_closer: int
    share_own_closer: float | None
    queries: int
    nn_queries: int
    nn_correct: int
    nn_share: float | None
    pairs_ok: int
    pairs_no_path: int


def _check_distance(item: object) -> PairDistance:
    if not isinstance(item, PairDistance):
        raise UmonsCompareError("the distances must be PairDistance values")
    if item.query.performer == item.reference.performer:
        raise UmonsCompareError("a performer is compared with themself")
    if item.query.side != item.reference.side:
        raise UmonsCompareError("a pair must be inside one side")
    if item.distance is not None:
        number = _number(item.distance)
        if number is None or number < 0.0:
            raise UmonsCompareError("a distance must be a finite number of 0 or more, or None")
    return item


def _median(values: Sequence[float]) -> float | None:
    return float(np.median(values)) if values else None


def summarise_classes(distances: Sequence[PairDistance]) -> ClassSummary:
    """The class table of ``distances`` (see ``ClassRow``) and the nearest-class result of every query: among the
    references with a distance, the smallest ``D``, a tie going to the lower class and then the lower id. Pairs of one
    performer or of two sides are refused. The order of the input does not matter."""
    own: dict[int, list[float]] = {}
    other: dict[int, list[float]] = {}
    own_none: dict[int, int] = {}
    other_none: dict[int, int] = {}
    candidates: dict[SegmentId, list[tuple[float, int, SegmentId]]] = {}
    queries: set[SegmentId] = set()
    ok = no_path = 0
    for item in (_check_distance(d) for d in distances):
        query, reference, d = item.query, item.reference, item.distance
        queries.add(query)
        same = query.klass == reference.klass
        if d is None:
            no_path += 1
            counts = own_none if same else other_none
            counts[query.klass] = counts.get(query.klass, 0) + 1
        else:
            ok += 1
            (own if same else other).setdefault(query.klass, []).append(float(d))
            candidates.setdefault(query, []).append((float(d), reference.klass, reference))
    correct: dict[int, int] = {}
    nearest: dict[int, int] = {}
    for query, found in candidates.items():
        best = min(found)
        nearest[query.klass] = nearest.get(query.klass, 0) + 1
        correct[query.klass] = correct.get(query.klass, 0) + (best[1] == query.klass)
    rows = []
    for klass in sorted({q.klass for q in queries}):
        own_median, other_median = _median(own.get(klass, [])), _median(other.get(klass, []))
        closer = None if own_median is None or other_median is None else own_median < other_median
        rows.append(
            ClassRow(
                klass=klass,
                queries=sum(q.klass == klass for q in queries),
                own_pairs=len(own.get(klass, [])),
                other_pairs=len(other.get(klass, [])),
                own_no_path=own_none.get(klass, 0),
                other_no_path=other_none.get(klass, 0),
                own_median=own_median,
                other_median=other_median,
                own_closer=closer,
                nn_queries=nearest.get(klass, 0),
                nn_correct=correct.get(klass, 0),
            )
        )
    compared = sum(r.own_closer is not None for r in rows)
    closer_count = sum(r.own_closer is True for r in rows)
    nn_queries, nn_correct = len(candidates), sum(correct.values())
    return ClassSummary(
        rows=tuple(rows),
        classes_compared=compared,
        classes_own_closer=closer_count,
        share_own_closer=closer_count / compared if compared else None,
        queries=len(queries),
        nn_queries=nn_queries,
        nn_correct=nn_correct,
        nn_share=nn_correct / nn_queries if nn_queries else None,
        pairs_ok=ok,
        pairs_no_path=no_path,
    )


@dataclass(frozen=True)
class ClassExperiment:
    """Everything of experiment 1: the inputs (settings, seed, counts), the chosen references and queries, the pairs
    (``available_pairs`` before the cap, ``planned_pairs`` after it, ``same_performer_skipped`` left out), the run and
    the summaries (all sides pooled, and each side)."""

    settings: AlignSettings
    seed: int
    references_per_group: int
    queries_per_group: int
    max_pairs: int | None
    references: Mapping[Group, tuple[SegmentId, ...]]
    queries: Mapping[Group, tuple[SegmentId, ...]]
    available_pairs: int
    planned_pairs: int
    same_performer_skipped: int
    run: ClassRun
    summary: ClassSummary
    by_side: Mapping[int, ClassSummary]


def classes_experiment(
    segments: Iterable[SegmentId],
    features_for: Callable[[str], FrameFeatures],
    *,
    settings: AlignSettings,
    seed: int,
    references: int = DEFAULT_REFERENCES,
    queries: int = DEFAULT_QUERIES,
    max_pairs: int | None = None,
    progress: Progress | None = None,
) -> ClassExperiment:
    """Experiment 1 over ``segments``: choose ``references`` and ``queries`` per class and side (the queries never a
    reference), plan the pairs, cap them to ``max_pairs`` (``None``: all), align, summarise (pooled and per side)."""
    pool = list(segments)
    reference_groups = select_segments(pool, per_group=references, seed=seed)
    taken = {s for group in reference_groups.values() for s in group}
    query_groups = select_segments(pool, per_group=queries, seed=seed, exclude=taken)
    plan = plan_pairs(reference_groups, query_groups)
    pairs = cap_pairs(plan.pairs, max_pairs, seed)
    run = run_classes(pairs, features_for, settings, progress)
    by_side = {
        side: summarise_classes([d for d in run.distances if d.query.side == side])
        for side in sorted({d.query.side for d in run.distances})
    }
    log.info("umons classes: %d pairs aligned, %d failed segments", len(run.distances), len(run.failed_segments))
    return ClassExperiment(
        settings=settings,
        seed=check_seed(seed),
        references_per_group=references,
        queries_per_group=queries,
        max_pairs=max_pairs,
        references=reference_groups,
        queries=query_groups,
        available_pairs=len(plan.pairs),
        planned_pairs=len(pairs),
        same_performer_skipped=plan.skipped_same_performer,
        run=run,
        summary=summarise_classes(run.distances),
        by_side=by_side,
    )


# --- experiment 2: the boundaries ------------------------------------------------------------------------------------
def _finite_interval(a: float, b: float, name: str) -> None:
    if _number(a) is None or _number(b) is None:
        raise UmonsCompareError(f"{name} must be finite numbers")


def temporal_iou(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    """The intersection over the union of ``[a_start, a_end)`` (``a_end >= a_start``: a moved part may have no length)
    and ``[b_start, b_end)`` (``b_end > b_start``), seconds; 0 for no overlap. ``UmonsCompareError`` for numbers that
    are not finite or intervals that are not."""
    _finite_interval(a_start, a_end, "the first interval")
    _finite_interval(b_start, b_end, "the second interval")
    if a_end < a_start:
        raise UmonsCompareError("the first interval ends before it starts")
    if not b_end > b_start:
        raise UmonsCompareError("the second interval must have a length above 0")
    inter = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    union = (a_end - a_start) + (b_end - b_start) - inter
    return inter / union


def _clock(values: object, name: str, order: str = "none") -> np.ndarray:
    """``values`` as a one-dimensional float64 array of finite seconds; ``order`` is ``none``, ``nondecreasing`` or
    ``increasing`` (strictly); ``UmonsCompareError`` otherwise."""
    try:
        array = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError):
        raise UmonsCompareError(f"{name} must be a one-dimensional array of seconds") from None
    if array.ndim != 1 or array.shape[0] < 1 or not np.isfinite(array).all():
        raise UmonsCompareError(f"{name} must be a one-dimensional array of finite seconds")
    steps = np.diff(array)
    if (order == "increasing" and (steps <= 0.0).any()) or (order == "nondecreasing" and (steps < 0.0).any()):
        raise UmonsCompareError(f"{name} must {'increase' if order == 'increasing' else 'never decrease'}")
    return array


def transfer_times(times: object, ref_t: object, matched: object) -> np.ndarray:
    """The query time of reference ``times`` (seconds): linear interpolation of ``matched`` (the query time of every
    reference row, never decreasing) over ``ref_t`` (the reference clock, strictly increasing, at least two rows). A
    time outside ``[ref_t[0], ref_t[-1]]`` is **NaN**, never clamped. ``UmonsCompareError`` for clocks that are not
    clocks."""
    t = _clock(times, "times")
    reference = _clock(ref_t, "the reference clock", "increasing")
    query = _clock(matched, "the matched clock", "nondecreasing")
    if reference.shape[0] < 2 or reference.shape != query.shape:
        raise UmonsCompareError("the reference and matched clocks need the same number of rows, at least two")
    moved = np.interp(t, reference, query)
    moved[(t < reference[0]) | (t > reference[-1])] = np.nan
    return moved


def uniform_times(times: object, ref_t: object, query_t: object) -> np.ndarray:
    """The reference line: ``times`` mapped linearly from the span of the reference clock to the span of the query clock
    (first row to last row), no warping; NaN outside the reference span."""
    reference = _clock(ref_t, "the reference clock", "increasing")
    query = _clock(query_t, "the query clock", "increasing")
    if reference.shape[0] < 2 or query.shape[0] < 2:
        raise UmonsCompareError("each clock needs at least two rows")
    return transfer_times(times, reference[[0, -1]], query[[0, -1]])


@dataclass(frozen=True)
class PartTransfer:
    """One labelled part carried from the reference to the query: ``rank`` its index in the label list, the label and
    its family, ``iou`` the temporal IoU of the moved part with the query's own part, the errors of the moved start
    and end (seconds, moved minus query), and the same three numbers for uniform scaling (``uniform_*``)."""

    reference: SequenceId
    query: SequenceId
    rank: int
    label: str
    family: str
    iou: float
    start_error_s: float
    end_error_s: float
    uniform_iou: float
    uniform_start_error_s: float
    uniform_end_error_s: float


@dataclass(frozen=True)
class PairBoundary:
    """One pair of recordings: ``status`` (``ok`` or ``no_path``), ``D`` (``None`` for no path), the parts measured, the
    parts left out (``parts_open``: the last part has no end; ``parts_outside``: a boundary outside the reference clock)
    and the lengths in grid rows."""

    reference: SequenceId
    query: SequenceId
    status: str
    distance: float | None
    parts: tuple[PartTransfer, ...]
    parts_open: int
    parts_outside: int
    reference_rows: int
    query_rows: int


def transfer_parts(
    alignment: Alignment,
    reference_rows: Sequence[LabelRow],
    query_rows: Sequence[LabelRow],
    reference_id: SequenceId,
    query_id: SequenceId,
) -> PairBoundary:
    """Carry every labelled part of the reference to the query through ``alignment.matched_query_times()`` and compare
    it with the query's part of the same rank (and, as a reference line, through uniform scaling). The label sequences
    must be equal (``UmonsCompareError`` otherwise). No path gives ``status="no_path"`` and no part."""
    if tuple(r.label for r in reference_rows) != tuple(r.label for r in query_rows):
        raise UmonsCompareError("the two label sequences differ: no part has a counterpart")
    reference_parts, query_parts = label_parts(reference_rows), label_parts(query_rows)
    ref_t, query_t = alignment.reference.t_sec, alignment.query.t_sec
    n_ref, n_query = len(ref_t), len(query_t)
    if alignment.result.status != "ok":
        return PairBoundary(reference_id, query_id, "no_path", None, (), 0, 0, n_ref, n_query)
    matched = alignment.matched_query_times()
    parts: list[PartTransfer] = []
    opened = outside = 0
    for rank, (rp, qp) in enumerate(zip(reference_parts, query_parts, strict=True)):
        if rp.family == "rest":
            continue
        if rp.end_s is None or qp.end_s is None:
            opened += 1
            continue
        bounds = np.array([rp.start_s, rp.end_s])
        moved = transfer_times(bounds, ref_t, matched)
        flat = uniform_times(bounds, ref_t, query_t)
        if np.isnan(moved).any() or np.isnan(flat).any():
            outside += 1
            continue
        parts.append(
            PartTransfer(
                reference=reference_id,
                query=query_id,
                rank=rank,
                label=rp.label,
                family=rp.family,
                iou=temporal_iou(float(moved[0]), float(moved[1]), qp.start_s, qp.end_s),
                start_error_s=float(moved[0]) - qp.start_s,
                end_error_s=float(moved[1]) - qp.end_s,
                uniform_iou=temporal_iou(float(flat[0]), float(flat[1]), qp.start_s, qp.end_s),
                uniform_start_error_s=float(flat[0]) - qp.start_s,
                uniform_end_error_s=float(flat[1]) - qp.end_s,
            )
        )
    return PairBoundary(reference_id, query_id, "ok", alignment.distance, tuple(parts), opened, outside, n_ref, n_query)


@dataclass(frozen=True)
class BoundaryCandidates:
    """The pairs of recordings that can be compared: ``usable`` (same capture, two performers, equal label sequences;
    ``(reference, query)`` with the lower id as the reference), how many pairs have different labels (left out), and how
    many labelled recordings have no Kinect file and the reverse."""

    usable: tuple[tuple[SequenceId, SequenceId], ...]
    different_labels: int
    labels_without_sequence: int
    sequences_without_labels: int


def candidate_pairs(
    labels: Mapping[SequenceId, Sequence[LabelRow]], available: Collection[SequenceId]
) -> BoundaryCandidates:
    """Pairs ``(a, b)``, ``a < b``, of recordings that have labels **and** a Kinect file (``available``), one capture,
    two performers; equal label sequences (in order, rests included) are usable, the others are counted."""
    have = set(available)
    both = sorted(set(labels) & have)
    usable: list[tuple[SequenceId, SequenceId]] = []
    different = 0
    for i, a in enumerate(both):
        for b in both[i + 1 :]:
            if a.capture != b.capture or a.performer == b.performer:
                continue
            if tuple(r.label for r in labels[a]) == tuple(r.label for r in labels[b]):
                usable.append((a, b))
            else:
                different += 1
    return BoundaryCandidates(tuple(usable), different, len(set(labels) - have), len(have - set(labels)))


@dataclass(frozen=True)
class BoundaryRun:
    """The alignments of a list of recording pairs: the pairs, the recordings whose features failed (id, error), the
    pairs whose alignment was refused (reference, query, error), the pairs skipped for a failed recording, and the
    seconds."""

    pairs: tuple[PairBoundary, ...]
    failed_sequences: tuple[tuple[str, str], ...]
    failed_pairs: tuple[tuple[str, str, str], ...]
    skipped_pairs: int
    seconds: float


def run_boundaries(
    pairs: Sequence[tuple[SequenceId, SequenceId]],
    labels: Mapping[SequenceId, Sequence[LabelRow]],
    features_for: Callable[[str], FrameFeatures],
    settings: AlignSettings,
    progress: Progress | None = None,
) -> BoundaryRun:
    """Align each ``(reference, query)`` and carry the boundaries (``transfer_parts``). Every pair needs labels for
    both recordings and equal label sequences (``UmonsCompareError`` before anything runs). Failures as in
    ``run_classes``."""
    for reference, query in pairs:
        if reference not in labels or query not in labels:
            raise UmonsCompareError("a recording of a pair has no label file")
        if tuple(r.label for r in labels[reference]) != tuple(r.label for r in labels[query]):
            raise UmonsCompareError("a pair has different label sequences")
    started = time.perf_counter()
    cache = _FeatureCache(features_for)
    results: list[PairBoundary] = []
    failed_pairs: list[tuple[str, str, str]] = []
    skipped = 0
    for done, (reference, query) in enumerate(pairs, start=1):
        reference_features, query_features = cache.get(reference.text), cache.get(query.text)
        if reference_features is None or query_features is None:
            skipped += 1
        else:
            try:
                alignment = align(
                    reference_features,
                    query_features,
                    min_visible=settings.min_visible,
                    band=settings.band,
                    step=settings.step,
                )
            except CompareError as exc:
                failed_pairs.append((reference.text, query.text, f"{type(exc).__name__}: {exc}"))
            else:
                results.append(transfer_parts(alignment, labels[reference], labels[query], reference, query))
        if progress is not None:
            progress(done, len(pairs))
    return BoundaryRun(
        tuple(results), tuple(cache.failed.items()), tuple(failed_pairs), skipped, time.perf_counter() - started
    )


@dataclass(frozen=True)
class BoundaryStats:
    """The numbers of a set of parts (``None`` when there is none): ``iou_*`` the median, the mean and the share with
    IoU at least 0.5; ``*_abs_*`` the median and the 90th percentile (linear between ranks) of the absolute error of
    the start and of the end in seconds; ``*_bias`` the median of the signed error (moved minus query)."""

    n: int
    iou_median: float | None
    iou_mean: float | None
    iou_share_half: float | None
    start_abs_median: float | None
    start_abs_p90: float | None
    end_abs_median: float | None
    end_abs_p90: float | None
    start_bias: float | None
    end_bias: float | None


@dataclass(frozen=True)
class BoundarySummary:
    """The pairs by status, the parts measured and left out, the statistics of the warped transfer (``stats``) and of
    uniform scaling (``uniform``) for ``all``, ``ex`` and ``tech``, and the median ``D`` of the pairs with a path."""

    pairs_ok: int
    pairs_no_path: int
    parts: int
    parts_open: int
    parts_outside: int
    stats: Mapping[str, BoundaryStats]
    uniform: Mapping[str, BoundaryStats]
    distance_median: float | None


def _stats(values: Sequence[tuple[float, float, float]]) -> BoundaryStats:
    if not values:
        return BoundaryStats(0, None, None, None, None, None, None, None, None, None)
    iou, start, end = (np.array([v[i] for v in values], dtype=np.float64) for i in range(3))
    return BoundaryStats(
        n=len(values),
        iou_median=float(np.median(iou)),
        iou_mean=float(np.mean(iou)),
        iou_share_half=float(np.mean(iou >= 0.5)),
        start_abs_median=float(np.median(np.abs(start))),
        start_abs_p90=float(np.percentile(np.abs(start), 90)),
        end_abs_median=float(np.median(np.abs(end))),
        end_abs_p90=float(np.percentile(np.abs(end), 90)),
        start_bias=float(np.median(start)),
        end_bias=float(np.median(end)),
    )


def summarise_boundaries(pairs: Sequence[PairBoundary]) -> BoundarySummary:
    """Pool the parts of ``pairs`` (each part counts once, however long its pair)."""
    parts = [p for pair in pairs for p in pair.parts]
    warped = {"all": parts, **{f: [p for p in parts if p.family == f] for f in FAMILIES}}
    stats = {k: _stats([(p.iou, p.start_error_s, p.end_error_s) for p in v]) for k, v in warped.items()}
    uniform = {
        k: _stats([(p.uniform_iou, p.uniform_start_error_s, p.uniform_end_error_s) for p in v])
        for k, v in warped.items()
    }
    distances = [pair.distance for pair in pairs if pair.distance is not None]
    return BoundarySummary(
        pairs_ok=sum(pair.status == "ok" for pair in pairs),
        pairs_no_path=sum(pair.status == "no_path" for pair in pairs),
        parts=len(parts),
        parts_open=sum(pair.parts_open for pair in pairs),
        parts_outside=sum(pair.parts_outside for pair in pairs),
        stats=stats,
        uniform=uniform,
        distance_median=_median(distances),
    )


@dataclass(frozen=True)
class BoundaryExperiment:
    """Everything of experiment 2: the inputs, the candidate pairs and what was left out, the run and the summary."""

    settings: AlignSettings
    seed: int
    max_pairs: int | None
    candidates: BoundaryCandidates
    run: BoundaryRun
    summary: BoundarySummary


def boundary_experiment(
    labels: Mapping[SequenceId, Sequence[LabelRow]],
    available: Collection[SequenceId],
    features_for: Callable[[str], FrameFeatures],
    *,
    settings: AlignSettings,
    seed: int,
    max_pairs: int | None = None,
    progress: Progress | None = None,
) -> BoundaryExperiment:
    """Experiment 2: the usable pairs (``candidate_pairs``), at most ``max_pairs`` of them by the seed, aligned and
    transferred, then summarised."""
    candidates = candidate_pairs(labels, available)
    pairs = cap_pairs(candidates.usable, max_pairs, seed)
    run = run_boundaries(pairs, labels, features_for, settings, progress)
    log.info("umons boundaries: %d pairs aligned, %d failed recordings", len(run.pairs), len(run.failed_sequences))
    return BoundaryExperiment(settings, check_seed(seed), max_pairs, candidates, run, summarise_boundaries(run.pairs))


# --- the tables and the CSV ------------------------------------------------------------------------------------------
def _num(value: float | None, digits: int = 4) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100.0 * value:.1f} %"


def _cell(value: float | None) -> str:
    """A CSV number: its shortest exact text, or an empty field."""
    return "" if value is None else repr(float(value))


def _table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return [*lines, ""]


def settings_line(settings: AlignSettings, seed: int) -> str:
    """The settings of a run as one line, written in every table (the run's inputs, not product values)."""
    return (
        f"Settings: min_visible {settings.min_visible} of {N_UNITS} units, band {settings.band:g}, "
        f"step {settings.step}, weights 1 for every unit, min_scale_s and min_segment_length not applied, "
        f"quality chain defaults, seed {seed}."
    )


_OUT_OF_DOMAIN = (
    "Out of domain: UMONS-TAICHI is 13 basic techniques seen by a Kinect (CC BY-NC-SA 4.0), not the 24 forms seen by a "
    "video pose; these numbers are not the product's accuracy."
)


def _class_rows(summary: ClassSummary) -> list[list[str]]:
    rows = []
    for r in summary.rows:
        ratio = None if not r.own_median or r.other_median is None else r.other_median / r.own_median
        closer = "n/a" if r.own_closer is None else ("yes" if r.own_closer else "no")
        rows.append(
            [
                f"G{r.klass:02d}",
                str(r.queries),
                str(r.own_pairs),
                str(r.other_pairs),
                _num(r.own_median),
                _num(r.other_median),
                _num(ratio, 2),
                closer,
                f"{r.nn_correct} / {r.nn_queries}",
                f"{r.own_no_path} / {r.other_no_path}",
            ]
        )
    return rows


_CLASS_HEADER = (
    "Class", "Queries", "Own pairs", "Other pairs", "Own median D", "Other median D", "Other / own", "Own closer",
    "Nearest correct", "No path own / other",
)  # fmt: skip


def _class_totals(summary: ClassSummary) -> str:
    return (
        f"Classes where the own class is closer: {summary.classes_own_closer} of {summary.classes_compared} "
        f"({_pct(summary.share_own_closer)}). Nearest-reference class correct: {summary.nn_correct} of "
        f"{summary.nn_queries} queries ({_pct(summary.nn_share)}). Pairs with a distance {summary.pairs_ok}, "
        f"with no path {summary.pairs_no_path}."
    )


def render_classes(exp: ClassExperiment) -> str:
    """Experiment 1 as Markdown: settings, sample, the class table pooled and per side, and the ids used. Numbers and
    dataset ids only."""
    run, out = exp.run, []
    out += ["## Classes: is the same class closer?", "", _OUT_OF_DOMAIN, "", settings_line(exp.settings, exp.seed), ""]
    cap = "no cap" if exp.max_pairs is None else f"capped to {exp.max_pairs}"
    out += [
        f"Sample: {exp.references_per_group} references and {exp.queries_per_group} queries per class and side; pairs "
        f"available {exp.available_pairs:,} ({cap}), aligned {len(run.distances):,}, left out because both were one "
        f"performer's {exp.same_performer_skipped:,}, skipped for a failed segment {run.skipped_pairs}, refused "
        f"{len(run.failed_pairs)}; segments that failed {len(run.failed_segments)}; {run.seconds:.1f} s.",
        "",
        "### Per class, both sides pooled",
        "",
        *_table(_CLASS_HEADER, _class_rows(exp.summary)),
        _class_totals(exp.summary),
        "",
    ]
    for side, summary in exp.by_side.items():
        out += [f"### Side D{side:02d}", "", *_table(_CLASS_HEADER, _class_rows(summary)), _class_totals(summary), ""]
    out += ["### Segments used", ""]
    rows = []
    for group in sorted(set(exp.references) | set(exp.queries)):
        refs = ", ".join(s.text for s in exp.references.get(group, ()))
        qrys = ", ".join(s.text for s in exp.queries.get(group, ()))
        rows.append([f"G{group[0]:02d}", f"D{group[1]:02d}", refs or "none", qrys or "none"])
    out += _table(("Class", "Side", "References", "Queries"), rows)
    if run.failed_segments or run.failed_pairs:
        out += ["### Failures", ""]
        out += _table(("Id", "Error"), [[i, e.replace("|", "/")] for i, e in run.failed_segments])
        out += _table(("Query", "Reference", "Error"), [[q, r, e.replace("|", "/")] for q, r, e in run.failed_pairs])
    return "\n".join(out) + "\n"


def _setting_columns(settings: AlignSettings) -> list[str]:
    return [str(settings.min_visible), repr(settings.band), settings.step]


_SETTING_NAMES: Final = ("min_visible", "band", "step")


def _csv(header: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def class_pairs_csv(exp: ClassExperiment) -> str:
    """One row per aligned pair: the ids, their classes, ``D`` (empty for no path), the status and the settings."""
    setting = _setting_columns(exp.settings)
    header = ("side", "query", "query_class", "reference", "reference_class", "distance", "status", *_SETTING_NAMES)
    rows = (
        [str(d.query.side), d.query.text, str(d.query.klass), d.reference.text, str(d.reference.klass),
         _cell(d.distance), d.status, *setting]
        for d in exp.run.distances
    )  # fmt: skip
    return _csv(header, rows)


def class_table_csv(exp: ClassExperiment) -> str:
    """One row per class for all sides pooled (``side`` = ``all``) and for each side: the numbers of ``ClassRow``."""
    setting = _setting_columns(exp.settings)
    header = (
        "side", "class", "queries", "own_pairs", "other_pairs", "own_no_path", "other_no_path", "own_median",
        "other_median", "own_closer", "nn_queries", "nn_correct", *_SETTING_NAMES,
    )  # fmt: skip
    rows = []
    for side, summary in (("all", exp.summary), *((str(s), v) for s, v in exp.by_side.items())):
        for r in summary.rows:
            closer = "" if r.own_closer is None else str(int(r.own_closer))
            rows.append(
                [side, str(r.klass), str(r.queries), str(r.own_pairs), str(r.other_pairs), str(r.own_no_path),
                 str(r.other_no_path), _cell(r.own_median), _cell(r.other_median), closer, str(r.nn_queries),
                 str(r.nn_correct), *setting]
            )  # fmt: skip
    return _csv(header, rows)


def class_selection_csv(exp: ClassExperiment) -> str:
    """The id of every segment chosen as a reference or a query, with its class and side."""
    rows = [
        [role, str(group[1]), str(group[0]), s.text]
        for role, chosen in (("reference", exp.references), ("query", exp.queries))
        for group in sorted(chosen)
        for s in chosen[group]
    ]
    return _csv(("role", "side", "class", "id"), rows)


def _stat_row(label: str, method: str, s: BoundaryStats) -> list[str]:
    return [
        label, method, str(s.n), _num(s.iou_median, 3), _num(s.iou_mean, 3), _pct(s.iou_share_half),
        _num(s.start_abs_median, 3), _num(s.start_abs_p90, 3), _num(s.end_abs_median, 3), _num(s.end_abs_p90, 3),
        _num(s.start_bias, 3), _num(s.end_bias, 3),
    ]  # fmt: skip


def render_boundaries(exp: BoundaryExperiment) -> str:
    """Experiment 2 as Markdown: settings, the pairs and what was left out, the IoU and error table (warped transfer
    and the uniform-scaling reference line) and the pairs by id. Numbers and dataset ids only."""
    run, s, c = exp.run, exp.summary, exp.candidates
    cap = "no cap" if exp.max_pairs is None else f"at most {exp.max_pairs}"
    out = ["## Boundaries: segment boundaries carried through the warping path", "", _OUT_OF_DOMAIN, ""]
    out += [settings_line(exp.settings, exp.seed), ""]
    out += [
        f"Pairs: {len(c.usable):,} usable (one capture, two performers, equal label sequences), {c.different_labels:,} "
        f"with different labels left out; {cap}; aligned {len(run.pairs)}, with a path {s.pairs_ok}, with no path "
        f"{s.pairs_no_path}, skipped for a failed recording {run.skipped_pairs}, refused {len(run.failed_pairs)}; "
        f"labelled recordings without a Kinect file {c.labels_without_sequence}, Kinect recordings without labels "
        f"{c.sequences_without_labels}; {run.seconds:.1f} s.",
        "",
        f"Parts measured {s.parts}; left out because the last part has no end {s.parts_open}, because a boundary lies "
        f"outside the reference clock {s.parts_outside}. Median D of the pairs with a path {_num(s.distance_median)}.",
        "",
        "### Temporal IoU and boundary errors (seconds; moved minus the query's own label)",
        "",
    ]
    header = (
        "Family", "Transfer", "Parts", "IoU median", "IoU mean", "IoU >= 0.5", "Start abs median", "Start abs p90",
        "End abs median", "End abs p90", "Start bias", "End bias",
    )  # fmt: skip
    rows = []
    for family in ("all", *FAMILIES):
        rows.append(_stat_row(family, "warping path", s.stats[family]))
        rows.append(_stat_row(family, "uniform scaling", s.uniform[family]))
    out += [*_table(header, rows), "### Pairs", ""]
    out += _table(
        ("Reference", "Query", "Status", "D", "Parts", "Open", "Outside", "Reference rows", "Query rows"),
        [
            [p.reference.text, p.query.text, p.status, _num(p.distance), str(len(p.parts)), str(p.parts_open),
             str(p.parts_outside), str(p.reference_rows), str(p.query_rows)]
            for p in run.pairs
        ],
    )  # fmt: skip
    if run.failed_sequences or run.failed_pairs:
        out += ["### Failures", ""]
        out += _table(("Id", "Error"), [[i, e.replace("|", "/")] for i, e in run.failed_sequences])
        out += _table(("Reference", "Query", "Error"), [[r, q, e.replace("|", "/")] for r, q, e in run.failed_pairs])
    return "\n".join(out) + "\n"


def boundaries_csv(exp: BoundaryExperiment) -> str:
    """One row per aligned pair: the ids, status, ``D``, the parts measured and left out, the lengths and the
    settings."""
    setting = _setting_columns(exp.settings)
    header = (
        "reference", "query", "status", "distance", "parts", "parts_open", "parts_outside", "reference_rows",
        "query_rows", *_SETTING_NAMES,
    )  # fmt: skip
    rows = (
        [p.reference.text, p.query.text, p.status, _cell(p.distance), str(len(p.parts)), str(p.parts_open),
         str(p.parts_outside), str(p.reference_rows), str(p.query_rows), *setting]
        for p in exp.run.pairs
    )  # fmt: skip
    return _csv(header, rows)


def boundary_parts_csv(exp: BoundaryExperiment) -> str:
    """One row per part measured: ids, rank, label, family, IoU and errors of the warped transfer and of uniform
    scaling, and the settings. No label time is written (derived numbers only)."""
    setting = _setting_columns(exp.settings)
    header = (
        "reference", "query", "rank", "label", "family", "iou", "start_error_s", "end_error_s", "uniform_iou",
        "uniform_start_error_s", "uniform_end_error_s", *_SETTING_NAMES,
    )  # fmt: skip
    rows = (
        [part.reference.text, part.query.text, str(part.rank), part.label, part.family, _cell(part.iou),
         _cell(part.start_error_s), _cell(part.end_error_s), _cell(part.uniform_iou),
         _cell(part.uniform_start_error_s), _cell(part.uniform_end_error_s), *setting]
        for pair in exp.run.pairs
        for part in pair.parts
    )  # fmt: skip
    return _csv(header, rows)
