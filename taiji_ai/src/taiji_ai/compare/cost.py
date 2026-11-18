"""The masked cost matrix between a query segment and a reference segment (W8, Appendix C.2, P6.02).

``cost_matrix(reference, query, *, min_visible, weights=None, block_rows=64)`` compares every frame ``i`` of the query
with every frame ``k`` of the reference, on the frame features of P6.01 (``compare.features``), and gives the matrix
that constrained DTW (P6.03a, ``compare.dtw``) runs on.

* **Orientation.** ``values`` is ``(n, m)``: **axis 0 is the query** (rows ``i``, ``n`` frames), **axis 1 the
  reference** (columns ``k``, ``m`` frames), as in Appendix C and in ``dtw``. A row or a column is a frame, not a time:
  the real clock stays in ``FrameFeatures.t_sec`` (AGENTS.md 5.2) and the cost is dimensionless.
* **Distance of a unit.** ``d_u(i, k)`` is the Euclidean norm of the difference of the two stored 2-vectors. For a
  *position* unit that is a distance in trunk lengths (the features are already normalised by the segment's own
  ``Λ``). For an *angle* unit the vectors are ``(sin φ, cos φ)``, so the norm is the chord
  ``2 |sin((a - b) / 2)|``, from 0 (the same direction) to 2 (opposite); no angle is ever unwrapped, so 359 degrees
  is 2 degrees from 1.
* **A cell** is the **weighted mean** of the unit distances over the units that have a weight above 0 and are valid in
  both frames: ``c(i, k) = Σ w_u d_u / Σ w_u``. Appendix C.2 writes "mean of ``w_j · ‖…‖``"; read as a weighted mean the
  scale of ``D`` does not change with the number of units that happen to be valid nor with a common factor of the
  weights (task P6.02, question Q1). The cell is **``+inf``** when fewer than ``min_visible`` such units exist: it
  cannot be used, and DTW does not step on it. A cell is never NaN and never 0 for lack of data (AGENTS.md 5.1). The
  count of common units is kept in ``n_common`` whatever the threshold.
* **Masks.** Only ``FrameFeatures.valid`` decides whether a unit takes part; the value stored under a false mask
  (NaN in the real features) is never read. A weight of 0 leaves the unit out of the mean *and* of the count. A bridged
  feature (a short gap that the quality stage filled and flagged) is a value and takes part like any other: the flag
  is for the report, not for the cost.
* **``min_visible`` has no default** (AGENTS.md 5.5; overview section 3.5): the caller passes it and the result echoes
  it. It is an integer from 1 to the number of units with a weight above 0. It counts every unit, positions and
  angles alike (an angle is evidence as much as a position).
* **Weights** default to 1 for every unit (no unit preferred). A mapping gives the weight of the units it names (an
  unknown name is refused, so a typo never passes) and every other unit keeps 1; per-action weights are the coach's
  (AGENTS.md 5.12) and arrive later with a record. A weight is a finite number of 0 or more. The result echoes the
  weights as used, one per unit in the units' order. The mean is computed with the weights divided by the largest, so
  that no sum can overflow; a positive weight whose share underflows to 0 is refused.
* **Inputs.** The two feature sets must have the same units (kind, name and joints, in the same order) and the same
  feature version: they are refused otherwise, never intersected. What each ``FrameFeatures`` says about itself is
  checked (shapes, a bool mask, a finite value wherever it is valid) so that NaN cannot get into the matrix.
* **Memory.** The matrix is built by blocks of ``block_rows`` query rows (``(b, m, U)`` arrays), never as the
  ``(n, m, U, 2)`` array (900 frames each and 21 units would be 260 MB); the result does not depend on the block size.

The arrays of the result are new and read-only; the inputs are never changed. Appendix C.2 is the design and nothing is
copied. Errors are ``CompareError`` naming the argument; a number or a type is echoed, never a string given by the
caller. A comparison that cannot be made for a reason of the data is ``+inf`` cells, not an error.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

import numpy as np

from taiji_ai.compare import CompareError
from taiji_ai.compare.features import FeatureUnit, FrameFeatures

_SHOWN_INTEGER_LIMIT: Final = 10**15  # an integer from here on is shown as a float (BUG-0080)
BLOCK_ROWS: Final = 64  # query rows per block: (64, m, U) float64 arrays, about 10 MB for 900 frames and 21 units


@dataclass(frozen=True, eq=False)
class CostMatrix:
    """The masked cost between a query and a reference; every array is a new read-only array.

    ``values`` ``(n, m)`` float64: axis 0 the query rows ``i``, axis 1 the reference rows ``k``; the weighted mean of
    the unit distances over the units valid in both frames (dimensionless: trunk lengths and chords), ``+inf`` where
    fewer than ``min_visible`` units are, never NaN. ``n_common`` ``(n, m)`` int16: the units with a weight valid in
    both frames (also in an ``+inf`` cell). ``units`` the names, equal in both feature sets and in the features' order;
    ``weights`` the weight of each unit as used (0: left out); ``min_visible`` as given; ``query_recording_id`` and
    ``reference_recording_id`` the provenance of the two feature sets and ``feature_version`` their common version.
    """

    values: np.ndarray
    n_common: np.ndarray
    units: tuple[str, ...]
    weights: tuple[float, ...]
    min_visible: int
    query_recording_id: str
    reference_recording_id: str
    feature_version: str


def _frozen(a: np.ndarray) -> np.ndarray:
    a.setflags(write=False)
    return a


def _is_integer(value: Any) -> bool:
    return isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, (bool, np.bool_))


def _shown(value: Any) -> str:
    """What an error says of an argument: the number itself, or only the type (never a string of the caller)."""
    if _is_integer(value):
        number = int(value)
        # from 10**15 on an integer is shown as a float (``inf`` beyond the float range), so a message stays short
        if abs(number) < _SHOWN_INTEGER_LIMIT:
            return repr(number)
        magnitude = _as_float(abs(number))  # ``_as_float`` gives +inf beyond the range, so the sign is taken here
        return repr(-magnitude if number < 0 else magnitude)
    return repr(float(value)) if _is_number(value) else type(value).__name__


def _describe(value: Any) -> str:
    return f"{value.dtype} array of shape {value.shape}" if isinstance(value, np.ndarray) else type(value).__name__


def _check_features(features: Any, name: str) -> None:
    """``CompareError`` unless ``features`` is a ``FrameFeatures`` whose arrays agree with each other and with its
    units, whose units are distinct, and whose valid features all have a finite value."""
    if not isinstance(features, FrameFeatures):
        raise CompareError(f"{name} must be a FrameFeatures, got {type(features).__name__}")
    values, valid, units = features.values, features.valid, features.units
    if not isinstance(values, np.ndarray) or values.dtype.kind != "f" or values.ndim != 3 or values.shape[2] != 2:
        raise CompareError(f"{name}.values must be a floating-point array of shape (N, U, 2), got {_describe(values)}")
    if not isinstance(valid, np.ndarray) or valid.dtype != np.bool_ or valid.shape != values.shape[:2]:
        raise CompareError(f"{name}.valid must be a bool array of shape {values.shape[:2]}, got {_describe(valid)}")
    if not isinstance(units, tuple) or not all(isinstance(u, FeatureUnit) for u in units):
        raise CompareError(f"{name}.units must be a tuple of FeatureUnit, got {type(units).__name__}")
    if len(units) != values.shape[1]:
        raise CompareError(
            f"{name}.units must have one entry per column of values ({values.shape[1]}), got {len(units)}"
        )
    if len({u.name for u in units}) != len(units):
        raise CompareError(f"{name}.units must have distinct names: a weight is given by name")
    finite = np.isfinite(values[valid]).all()  # a feature that says it is valid and has no value is a producer defect
    if not finite:
        raise CompareError(f"{name}: a valid feature has a non-finite value (it must be marked not valid instead)")


def _same_units(reference: FrameFeatures, query: FrameFeatures) -> tuple[str, ...]:
    """The names of the units, once the two feature sets are shown to have the same units (and version)."""
    ref = [(u.kind, u.name, tuple(u.joints)) for u in reference.units]
    qry = [(u.kind, u.name, tuple(u.joints)) for u in query.units]
    if len(ref) != len(qry):
        raise CompareError(
            f"reference and query must have the same units: the reference has {len(ref)} and the query {len(qry)}"
        )
    for index, (a, b) in enumerate(zip(ref, qry, strict=True)):
        if a != b:
            raise CompareError(f"reference and query must have the same units in the same order: unit {index} differs")
    if reference.version != query.version:
        raise CompareError("reference and query must have the same feature version: they were made by different rules")
    return tuple(name for _, name, _ in ref)


def _check_min_visible(min_visible: Any) -> int:
    if not _is_integer(min_visible) or min_visible < 1:
        raise CompareError(f"min_visible must be an integer of at least 1, got {_shown(min_visible)}")
    return int(min_visible)


def _check_block_rows(block_rows: Any) -> int:
    if not _is_integer(block_rows) or block_rows < 1:
        raise CompareError(f"block_rows must be an integer of at least 1, got {_shown(block_rows)}")
    return int(block_rows)


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except OverflowError:  # an integer too large for a float is not a finite weight
        return math.inf


def _weights_of(weights: Any, names: tuple[str, ...]) -> tuple[float, ...]:
    """One weight per unit: 1 by default (``None``, or a unit the mapping does not name); ``CompareError`` if bad."""
    if weights is None:
        return (1.0,) * len(names)
    if not isinstance(weights, Mapping):
        raise CompareError(f"weights must be None or a mapping of unit name to weight, got {type(weights).__name__}")
    position = {name: index for index, name in enumerate(names)}
    chosen = [1.0] * len(names)
    for number, (key, value) in enumerate(weights.items()):
        if not isinstance(key, str) or key not in position:
            raise CompareError(f"weights: key number {number} is not the name of a unit of the features")
        weight = _as_float(value) if _is_number(value) else math.nan
        if not math.isfinite(weight) or weight < 0.0:  # NaN, infinity and a non-number all fail the first test
            raise CompareError(
                f"weights for unit {position[key]} must be a finite number of 0 or more, got {_shown(value)}"
            )
        chosen[position[key]] = weight
    return tuple(chosen)


def _share_of(weights: tuple[float, ...], min_visible: int) -> np.ndarray:
    """The weights divided by the largest (float64, in [0, 1]); ``CompareError`` when ``min_visible`` is above the
    number of weighted units or when the share of a weighted unit underflows to 0."""
    w = np.array(weights, dtype=np.float64)
    weighted = int((w > 0.0).sum())
    if min_visible > weighted:
        raise CompareError(
            f"min_visible ({_shown(min_visible)}) must be at most the number of units with a weight above 0 "
            f"({weighted}): check weights"
        )
    share = w / w.max()
    if ((w > 0.0) & (share == 0.0)).any():
        raise CompareError("weights: a positive weight is smaller than the largest by more than a float can hold")
    return share


def cost_matrix(
    reference: FrameFeatures,
    query: FrameFeatures,
    *,
    min_visible: int,
    weights: Mapping[str, float] | None = None,
    block_rows: int = BLOCK_ROWS,
) -> CostMatrix:
    """The masked cost of every query frame against every reference frame (see the module docstring for every rule).

    ``reference`` and ``query``: ``FrameFeatures`` with the same units and version (positions in trunk lengths, angles
    as ``(sin, cos)``). ``min_visible``: the least number of units with a weight above 0 valid in both frames for a
    cell to be a value; an integer, with no default. ``weights``: ``None`` (1 for every unit) or a mapping of unit name
    to a finite weight of 0 or more (a unit that is not named keeps 1; 0 leaves it out). ``block_rows``: query rows per
    block, only a limit on memory (the result does not depend on it). Returns a ``CostMatrix`` of ``(n, m)`` arrays with
    ``n`` the query frames and ``m`` the reference frames; neither input is changed. ``CompareError`` naming the
    argument for anything it cannot use.
    """
    _check_features(reference, "reference")
    _check_features(query, "query")
    visible = _check_min_visible(min_visible)
    rows = _check_block_rows(block_rows)
    names = _same_units(reference, query)
    weight_of = _weights_of(weights, names)
    share = _share_of(weight_of, visible)
    used = np.array(weight_of) > 0.0
    n, m = query.valid.shape[0], reference.valid.shape[0]
    # a value under a false mask is never read: the zero below is a placeholder that ``common`` excludes, not data
    qx, qy = (np.where(query.valid, query.values[:, :, axis], 0.0) for axis in (0, 1))  # (n, U)
    rx, ry = (np.where(reference.valid, reference.values[:, :, axis], 0.0) for axis in (0, 1))  # (m, U)
    query_used = query.valid & used  # (n, U): the units that count in a query frame
    values = np.full((n, m), math.inf)
    n_common = np.zeros((n, m), dtype=np.int16)
    for first in range(0, n, rows):
        block = slice(first, min(first + rows, n))
        common = query_used[block, None, :] & reference.valid[None, :, :]  # (b, m, U): valid in both, with a weight
        distance = qx[block, None, :] - rx[None, :, :]  # (b, m, U) x difference, reused for the norm
        np.hypot(distance, qy[block, None, :] - ry[None, :, :], out=distance)  # position: norm; angle: the chord
        distance *= share
        np.copyto(distance, 0.0, where=~common)  # a unit that is not common (or has no weight) adds nothing
        count = common.sum(axis=-1, dtype=np.int16)
        total = np.where(common, share, 0.0).sum(axis=-1)
        np.divide(distance.sum(axis=-1), total, out=values[block], where=count >= visible)  # else it stays +inf
        n_common[block] = count
    return CostMatrix(
        values=_frozen(values),
        n_common=_frozen(n_common),
        units=names,
        weights=weight_of,
        min_visible=visible,
        query_recording_id=query.recording_id,
        reference_recording_id=reference.recording_id,
        feature_version=reference.version,
    )
