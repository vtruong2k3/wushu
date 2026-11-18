"""The "normal band" of a movement from several reference takes, and where a trainee's distance lies against it (W8,
Appendix C.5, P6.06).

A shape distance ``D`` (Appendix C.4) means nothing alone: a coach's own takes of one movement differ from each other
too. With two or more reference takes, the distances **between** them are the band of what the coach himself does; the
trainee's distances to those takes are then put against it. This module only describes: it gives the band, the
trainee's value and whether the value is below, within or above the band, with its ratio to the top of the band.
**It never gives a score from 0 to 100 and no label such as good or bad**: a label needs a signed ``metric_record``
(AGENTS.md section 5.5).

It works on plain values and does not run an alignment: the caller aligns every pair of takes (P6.03b) and passes one
``Comparison`` per alignment. ``distance`` is ``D`` of an alignment, the plain mean of the cost over the path
(``DtwResult.distance``, overview section 3.3), dimensionless (trunk lengths and chords). It is **never** the
``normalised`` value of a ``symmetricP1`` result, which is not ``D``. A distance is comparable with another only if the
two were made with the same settings (features, weights, ``min_visible``, band, step pattern): ``Comparison.settings``
carries them (``Alignment.settings``) and every setting must be equal across the band and the trainee, or the call is
refused naming the setting that differs.

**The references.** They are the segment IDs found in ``between_references`` and the ``reference_id`` of the trainee's
comparisons, in sorted order (so the result does not depend on the order or the direction of the caller's lists). A
pair is unordered and **every pair** of the references must be given exactly once; the trainee must be compared with
**every** reference exactly once, as one segment. A band from some of the pairs would depend on which ones were run, so
an incomplete or repeated set is refused naming the pair, never completed or averaged. One reference has no pair: it is
the empty ``between_references`` with the trainee compared with it.

**The band** is the smallest, the median and the largest of the finite distances between the pairs (with two to five
takes a percentile would be invented precision). **The trainee's value** is the median of its finite distances to the
references (like with like: each is a distance between two takes, as the band's are). The position is ``below`` when the
value is under the smallest distance, ``above`` when it is over the largest, and ``within`` otherwise, **both ends
included**; ``ratio_to_high`` is the value over the largest distance (``None`` when that is 0, identical takes).

**No path is not zero.** A distance of ``None`` (the alignment found no path) is left out and counted
(``n_pairs_without_path``); the trainee's ``None`` stays in its place of ``trainee_distances``. Statuses, in this order:
``insufficient_references`` when no pair has a finite distance (fewer than two references have no pair at all): the
band, the position and the ratio are ``None`` and the trainee's own distances are still echoed; ``no_trainee_distance``
when the band exists but the trainee has no finite distance: the band is reported, the value, position and ratio are
``None``; ``ok`` otherwise.

Errors are ``CompareError`` naming the argument and the place (``between_references[2].settings``); a message names the
setting names and the IDs only after they were checked to be short codes, and never echoes a path, a file name or any
other text the caller passed. The module logs nothing. Sources of the idea: Appendix C.5 and W8 of
``Docs/TECH_WORKFLOW_V1.md`` (no third-party code).
"""

from __future__ import annotations

import itertools
import math
import re
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

import numpy as np

from taiji_ai.compare import CompareError

# A segment ID or the name of a setting: a short code, never a path, a file name or free text (as the other modules).
_CODE: Final = re.compile(r"[A-Za-z0-9_.-]{1,64}")


@dataclass(frozen=True)
class Comparison:
    """One alignment of two segments, as P6.06 reads it.

    ``reference_id`` and ``query_id`` are short codes of the two segments (pseudonymous IDs, never names or paths);
    between two references either may be first. ``distance`` is ``D`` of the alignment (dimensionless; a finite number
    of at least 0) or ``None`` when no path was found. ``settings`` is ``Alignment.settings``: a non-empty mapping from
    short-code names to the plain values that decide ``D``; it must be equal across a band.
    """

    reference_id: str
    query_id: str
    distance: float | None
    settings: Mapping[str, object]


@dataclass(frozen=True)
class ReferenceBand:
    """Where a trainee's distance lies against the band of the reference takes (a description, never a score).

    ``references`` the sorted segment IDs of the references; ``n_pairs`` the number of pairs given (``k (k - 1) / 2``
    for ``k`` references) and ``n_pairs_without_path`` of them with no distance. ``band_low``, ``band_median`` and
    ``band_high``: the smallest, median and largest finite distance between the pairs. ``trainee_distances``: the
    trainee's distance to each reference, in the order of ``references``, ``None`` where there was no path.
    ``trainee_value``: the median of the finite ones. ``position``: ``below``, ``within`` (both ends included) or
    ``above``. ``ratio_to_high``: ``trainee_value / band_high``. Every number is a dimensionless ``D``, or a ratio of
    two of them. A field is ``None`` when it cannot be computed for the ``status`` (see the module docstring).
    """

    status: Literal["ok", "insufficient_references", "no_trainee_distance"]
    references: tuple[str, ...]
    n_pairs: int
    n_pairs_without_path: int
    band_low: float | None
    band_median: float | None
    band_high: float | None
    trainee_distances: tuple[float | None, ...]
    trainee_value: float | None
    position: Literal["below", "within", "above"] | None
    ratio_to_high: float | None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, (bool, np.bool_))


def _as_float(value: Any) -> float | None:
    """The number as a float, or ``None`` when it is not a number (or an integer too large for a float)."""
    if not _is_number(value):
        return None
    try:
        return float(value)
    except OverflowError:
        return None


def _what(value: Any) -> str:
    """How a refused value is named in a message: a number as it is, anything else by its type, never by its text."""
    number = _as_float(value)
    return type(value).__name__ if number is None else repr(number)


@dataclass(frozen=True)
class _Checked:
    """A ``Comparison`` after its fields were checked: ``where`` names its place in the arguments of a message."""

    where: str
    reference_id: str
    query_id: str
    distance: float | None
    settings: Mapping[str, object]


def _check_comparisons(value: Any, name: str) -> tuple[Comparison, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CompareError(f"{name} must be a list or tuple of Comparison, got {type(value).__name__}")
    items = tuple(value)
    for index, item in enumerate(items):
        if not isinstance(item, Comparison):
            raise CompareError(f"{name}[{index}] must be a Comparison, got {type(item).__name__}")
    return items


def _check_id(value: Any, where: str, field: str) -> str:
    if not isinstance(value, str) or _CODE.fullmatch(value) is None:
        kind = "a string that is not a short code" if isinstance(value, str) else type(value).__name__
        raise CompareError(
            f"{where}.{field} must be a short code of 1 to 64 letters, digits, '_', '.' or '-' "
            f"(not a path or a name), got {kind}"
        )
    return value


def _check_distance(value: Any, where: str) -> float | None:
    if value is None:
        return None
    number = _as_float(value)
    if number is None or not math.isfinite(number) or number < 0.0:
        raise CompareError(
            f"{where}.distance must be None (no path) or a finite number of at least 0, got {_what(value)}"
        )
    return number


def _check_settings(value: Any, where: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not value:
        raise CompareError(f"{where}.settings must be a non-empty mapping of the settings that made the distance")
    for key in value:
        if not isinstance(key, str) or _CODE.fullmatch(key) is None:
            raise CompareError(
                f"{where}.settings has a name that is not a short code of 1 to 64 letters, digits, '_', '.' or '-'"
            )
    return value


def _check_comparison(c: Comparison, where: str) -> _Checked:
    reference_id = _check_id(c.reference_id, where, "reference_id")
    query_id = _check_id(c.query_id, where, "query_id")
    if reference_id == query_id:
        raise CompareError(f"{where} compares the segment '{reference_id}' with itself")
    return _Checked(
        where, reference_id, query_id, _check_distance(c.distance, where), _check_settings(c.settings, where)
    )


def _equal(a: Any, b: Any) -> bool:
    """Equality by value, extended to arrays and to mappings and sequences that hold arrays (``==`` raises on those).

    A list and a tuple with equal items are equal: a JSON round trip turns tuples into lists.
    """
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return bool(np.array_equal(a, b))
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        return a.keys() == b.keys() and all(_equal(a[key], b[key]) for key in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b, strict=True))
    return bool(a == b)


def _check_same_settings(everything: Sequence[_Checked]) -> None:
    """Every comparison was made with the settings of the first one, or ``CompareError`` naming the ones that differ."""
    if not everything:
        return
    first = everything[0]
    for other in everything[1:]:
        names = first.settings.keys() | other.settings.keys()
        differ = sorted(
            key
            for key in names
            if key not in first.settings
            or key not in other.settings
            or not _equal(first.settings[key], other.settings[key])
        )
        if differ:
            raise CompareError(f"{other.where}.settings differs from {first.where}.settings in: {', '.join(differ)}")


def _pair_distances(pairs: Sequence[_Checked]) -> dict[tuple[str, str], float | None]:
    """The distance of every unordered pair of segments (the smaller ID first); a pair given twice is refused."""
    distances: dict[tuple[str, str], float | None] = {}
    for c in pairs:
        pair = (min(c.reference_id, c.query_id), max(c.reference_id, c.query_id))
        if pair in distances:
            raise CompareError(f"{c.where} repeats the pair ('{pair[0]}', '{pair[1]}'): each pair is given once")
        distances[pair] = c.distance
    return distances


def _trainee_distances(trainee: Sequence[_Checked]) -> tuple[str | None, dict[str, float | None]]:
    """``(the trainee's ID, {reference: distance})``: one trainee, each reference once."""
    trainee_id = trainee[0].query_id if trainee else None
    distances: dict[str, float | None] = {}
    for c in trainee:
        if c.query_id != trainee_id:
            raise CompareError(
                f"{c.where}.query_id ('{c.query_id}') differs from trainee[0].query_id ('{trainee_id}'): "
                "the trainee is one segment"
            )
        if c.reference_id in distances:
            raise CompareError(f"{c.where} compares the trainee a second time with the reference '{c.reference_id}'")
        distances[c.reference_id] = c.distance
    return trainee_id, distances


def _more(items: Sequence[object]) -> str:
    return f" (and {len(items) - 1} more)" if len(items) > 1 else ""


def reference_band(between_references: Sequence[Comparison], trainee: Sequence[Comparison]) -> ReferenceBand:
    """The band of the references' own distances and where the trainee's distance lies against it.

    ``between_references``: one ``Comparison`` for **every** pair of the references (each pair once, either direction).
    ``trainee``: one ``Comparison`` for every reference (the trainee as ``query_id`` in all of them, the reference as
    ``reference_id``). Both are lists or tuples; they are not changed. Distances are ``D`` (dimensionless), ``None``
    for no path; ``settings`` must be equal in every ``Comparison``. Returns a ``ReferenceBand``; see the module
    docstring for the band, the value, the position, the ratio and the statuses (``ok``, ``insufficient_references``,
    ``no_trainee_distance``). ``CompareError`` for an argument that is not a list of ``Comparison``, an ID that is not
    a short code, a distance that is not ``None`` or a finite number of at least 0, empty or unequal ``settings``, a
    pair given twice or missing, a trainee that is a reference, has more than one ID or is compared twice with a
    reference or not with every one.
    """
    between_in = _check_comparisons(between_references, "between_references")
    trainee_in = _check_comparisons(trainee, "trainee")
    pairs = [_check_comparison(c, f"between_references[{i}]") for i, c in enumerate(between_in)]
    own = [_check_comparison(c, f"trainee[{i}]") for i, c in enumerate(trainee_in)]
    _check_same_settings(pairs + own)

    pair_distance = _pair_distances(pairs)
    in_pairs = set(itertools.chain.from_iterable(pair_distance))
    trainee_id, trainee_distance = _trainee_distances(own)
    if trainee_id in in_pairs:
        raise CompareError(f"the trainee '{trainee_id}' is one of the references of between_references")

    references = tuple(sorted(in_pairs | set(trainee_distance)))
    missing_pairs = [pair for pair in itertools.combinations(references, 2) if pair not in pair_distance]
    if missing_pairs:
        raise CompareError(
            f"between_references lacks the pair ('{missing_pairs[0][0]}', '{missing_pairs[0][1]}')"
            f"{_more(missing_pairs)}: every pair of the references is needed"
        )
    absent = [reference for reference in references if reference not in trainee_distance]
    if absent:
        raise CompareError(
            f"trainee has no comparison with the reference '{absent[0]}'{_more(absent)}: "
            "it is compared with every reference"
        )

    finite_pairs = [d for d in pair_distance.values() if d is not None]
    distances = tuple(trainee_distance[reference] for reference in references)
    finite_trainee = [d for d in distances if d is not None]
    value = statistics.median(finite_trainee) if finite_trainee else None
    n_pairs, without_path = len(pair_distance), len(pair_distance) - len(finite_pairs)

    if not finite_pairs:  # fewer than two references have no pair at all
        return ReferenceBand(
            status="insufficient_references",
            references=references,
            n_pairs=n_pairs,
            n_pairs_without_path=without_path,
            band_low=None,
            band_median=None,
            band_high=None,
            trainee_distances=distances,
            trainee_value=value,
            position=None,
            ratio_to_high=None,
        )
    low, median, high = min(finite_pairs), statistics.median(finite_pairs), max(finite_pairs)
    if value is None:
        return ReferenceBand(
            status="no_trainee_distance",
            references=references,
            n_pairs=n_pairs,
            n_pairs_without_path=without_path,
            band_low=low,
            band_median=median,
            band_high=high,
            trainee_distances=distances,
            trainee_value=None,
            position=None,
            ratio_to_high=None,
        )
    position: Literal["below", "within", "above"] = "below" if value < low else "above" if value > high else "within"
    return ReferenceBand(
        status="ok",
        references=references,
        n_pairs=n_pairs,
        n_pairs_without_path=without_path,
        band_low=low,
        band_median=median,
        band_high=high,
        trainee_distances=distances,
        trainee_value=value,
        position=position,
        ratio_to_high=value / high if high > 0.0 else None,
    )
