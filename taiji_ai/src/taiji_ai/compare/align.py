"""The alignment of a query segment with a reference segment: frame features, masked cost and constrained DTW in one
call (W8, Appendix C, P6.03b).

``align(reference, query, *, min_visible, band, step="symmetricP1", weights=None)`` is **exactly**
``dtw(cost_matrix(reference, query, min_visible=..., weights=...), band=..., step=...)``: the cost of P6.02
(``compare.cost``) between the frame features of P6.01 (``compare.features``), and the path and the shape distance ``D``
of P6.03a (``compare.dtw``). It adds no rule of its own to the cost or the path; what it returns, ``Alignment``, keeps
the two feature sets, the cost, the result and the **settings** that made ``D``, so that a later step (the local tempo
of P6.04, the check on UMONS of P6.07, the band of P6.06) needs nothing else.

* **Orientation.** As everywhere in ``compare``: the cost is ``(n, m)`` with **axis 0 the query** (rows ``i``) and
  **axis 1 the reference** (rows ``k``); a path cell is ``(i, k)``. A row is a frame, not a time: the real clock is
  ``FrameFeatures.t_sec`` of each segment (AGENTS.md 5.2) and shape, not tempo, is what DTW compares (W8).
* **Settings** (``Alignment.settings``) are the fingerprint of a distance: a read-only, **non-empty** mapping with the
  short-code names ``feature_version`` (the features' version), ``units`` (the unit names, a tuple), ``weights`` (one
  float per unit, as the cost echoes them, a tuple), ``min_visible`` (int), ``band`` (float), ``step`` (str),
  ``min_scale_s`` and ``min_segment_length`` (the two echoes of ``frame_features``: a float, or ``None`` when no minimum
  was applied). The values are plain Python objects (numbers, strings, ``None``, tuples), never numpy scalars. Two
  distances are comparable only if their settings are equal (P6.06 refuses otherwise). Because a feature that is not a
  value depends on those two minimums, **the reference and the query must have been made with the same**
  ``min_scale_s`` and ``min_segment_length``: ``align`` refuses two feature sets that differ in either, naming it.
  The camera roll (taken out of each segment separately) and the lengths ``n`` and ``m`` are not settings.
* **``matched_query_times()``** gives, for every reference row, the **mean of the query's real time** (``query.t_sec``,
  seconds) over the cells of the path on that row: a horizontal run of the path (one query row, several reference rows)
  gives that one query time to each of its rows, a vertical run (several query rows on one reference row) averages them.
  P6.04 fits the local tempo to it and P6.07 carries boundaries with it, so the mapping is written once, here. It is
  computed from the real clock, never from row indices, and is NaN in every row when there is no path (never 0).
* **``as_comparison(reference_id, query_id)``** gives the ``Comparison`` of P6.06 (``compare.reference_band``): the two
  segment IDs (short codes, never a path or a name), ``D`` and the settings. ``D`` is ``DtwResult.distance``, the plain
  mean of the cost over the path, **never** ``DtwResult.normalised`` (which, for ``symmetricP1``, is not ``D``); it is
  ``None`` when there is no path. ``align.py`` imports ``Comparison``; ``reference_band.py`` never imports this
  module.
* **No path is a result, not an error** (``result.status == "no_path"``, ``distance`` ``None``, every matched time NaN).
  **``align`` runs no guard**: whether two segments may be compared at all (same action, side, variant and view, enough
  coverage) is decided by the caller with ``compare.guards.check_comparable`` first; features carry no description of
  the movement, so ``align`` aligns whatever it is handed.
* **Clock.** ``t_sec`` of each feature set must be a one-dimensional finite strictly increasing float array with one
  entry per row: the cost does not read it but ``matched_query_times`` and P6.04 do.

``min_visible`` and ``band`` have no default (AGENTS.md 5.5; overview section 3.5): the caller passes them and the
settings echo them. The refusals of the parts (units, version, ``min_visible``, weights, band, step) are theirs and pass
through with their own message; the band and the step are checked by ``dtw`` after the cost was built. Arrays of the
result are new and read-only; the inputs are never changed. Errors are ``CompareError`` naming the argument; a number
or a type is echoed, never a string given by the caller. Appendix C is the design; no third-party code is used.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

import numpy as np

from taiji_ai.compare import CompareError
from taiji_ai.compare.cost import CostMatrix, cost_matrix
from taiji_ai.compare.dtw import DtwResult, dtw
from taiji_ai.compare.features import FrameFeatures
from taiji_ai.compare.reference_band import Comparison

# A segment ID: a short code, never a path, a file name or free text. It is the pattern of ``reference_band``, which
# checks the IDs of the ``Comparison`` it is given (a test pins that the two agree).
_CODE: Final = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_MINIMUMS: Final = ("min_scale_s", "min_segment_length")  # the features' echoes that must be equal in the two sets


def _frozen(a: np.ndarray) -> np.ndarray:
    a.setflags(write=False)
    return a


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, (bool, np.bool_))


def _shown(value: Any) -> str:
    """What an error says of a value: ``None``, the number itself, or only the type (never a string of the caller)."""
    if value is None:
        return "None"
    try:
        return repr(float(value)) if _is_number(value) else type(value).__name__
    except OverflowError:  # an integer too large for a float
        return type(value).__name__


def _finite(value: Any) -> float | None:
    """``value`` as a finite float, or ``None`` when it is not a finite number (an integer too large for a float is
    not one)."""
    if not _is_number(value):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _describe(value: Any) -> str:
    return f"{value.dtype} array of shape {value.shape}" if isinstance(value, np.ndarray) else type(value).__name__


def _check_features(features: Any, name: str) -> FrameFeatures:
    if not isinstance(features, FrameFeatures):
        raise CompareError(f"{name} must be a FrameFeatures, got {type(features).__name__}")
    return features


def _minimum(features: FrameFeatures, owner: str, setting: str) -> float | None:
    """The echo ``setting`` of ``features`` as ``None`` or a float; ``CompareError`` if it is neither ``None`` nor a
    finite number."""
    value = getattr(features, setting)
    if value is None:
        return None
    number = _finite(value)
    if number is None:
        raise CompareError(f"{owner}.{setting} must be None or a finite number, got {_shown(value)}")
    return number


def _same_minimums(reference: FrameFeatures, query: FrameFeatures) -> dict[str, float | None]:
    """The two minimums that both feature sets were made with, or ``CompareError`` naming the one that differs."""
    chosen: dict[str, float | None] = {}
    for setting in _MINIMUMS:
        mine, theirs = _minimum(reference, "reference", setting), _minimum(query, "query", setting)
        if mine != theirs:
            raise CompareError(
                f"reference and query must be made with the same {setting} (reference {_shown(mine)}, query "
                f"{_shown(theirs)}): features that are values under different minimums are not compared"
            )
        chosen[setting] = mine
    return chosen


def _check_clock(features: FrameFeatures, name: str) -> None:
    """``CompareError`` unless ``t_sec`` is a one-dimensional finite strictly increasing float array, one per row."""
    t = features.t_sec
    if not isinstance(t, np.ndarray) or t.dtype.kind != "f" or t.ndim != 1:
        raise CompareError(f"{name}.t_sec must be a one-dimensional float array, got {_describe(t)}")
    rows = features.values.shape[0]
    if t.shape[0] != rows:
        raise CompareError(f"{name}.t_sec must have one entry per row of values ({rows}), got {t.shape[0]}")
    if not np.isfinite(t).all():
        raise CompareError(f"{name}.t_sec must be finite: it is the real clock in seconds")
    if (np.diff(t) <= 0.0).any():
        raise CompareError(f"{name}.t_sec must be strictly increasing: it is the real clock in seconds")


def _check_id(value: Any, argument: str) -> str:
    if not isinstance(value, str) or _CODE.fullmatch(value) is None:
        kind = "a string that is not a short code" if isinstance(value, str) else type(value).__name__
        raise CompareError(
            f"{argument} must be a short code of 1 to 64 letters, digits, '_', '.' or '-' (not a path or a name), "
            f"got {kind}"
        )
    return value


@dataclass(frozen=True, eq=False)
class Alignment:
    """One query segment aligned with one reference segment, with everything that made ``D``.

    ``reference`` and ``query`` the two ``FrameFeatures`` as given; ``cost`` the ``CostMatrix`` ``(n, m)`` (axis 0 the
    query, axis 1 the reference); ``result`` the ``DtwResult`` on it (path cells ``(query row, reference row)``,
    ``D`` in ``distance``); ``settings`` the read-only, non-empty mapping of the settings that decided ``D`` (the
    module docstring lists the names and the kinds of value).
    """

    reference: FrameFeatures
    query: FrameFeatures
    cost: CostMatrix
    result: DtwResult
    settings: Mapping[str, object]

    @property
    def distance(self) -> float | None:
        """``D`` (``DtwResult.distance``: the plain mean of the cost over the path; dimensionless) or ``None``."""
        return self.result.distance

    def matched_query_times(self) -> np.ndarray:
        """``(m,)`` float64 read-only seconds: for every reference row ``k``, the mean of ``query.t_sec[i]`` over the
        path cells ``(i, k)`` on that row; NaN in every row when there is no path. A new array on every call."""
        rows = self.cost.values.shape[1]
        matched = np.full(rows, math.nan)
        if self.result.status == "ok":
            path = self.result.path
            query_row, reference_row = path[:, 0], path[:, 1]
            total = np.bincount(reference_row, weights=self.query.t_sec[query_row], minlength=rows)
            count = np.bincount(reference_row, minlength=rows)
            # every reference row has a cell on a path from corner to corner; ``where`` only keeps a NaN, never a 0
            np.divide(total, count, out=matched, where=count > 0)
        return _frozen(matched)

    def as_comparison(self, reference_id: str, query_id: str) -> Comparison:
        """The ``Comparison`` of P6.06: the two segment IDs, ``D`` (``None`` for no path; never ``normalised``) and the
        settings. The IDs are short codes of 1 to 64 letters, digits, ``_``, ``.`` or ``-`` (``CompareError`` naming the
        argument otherwise); equal IDs are not refused here (``reference_band`` refuses a segment against itself)."""
        return Comparison(
            reference_id=_check_id(reference_id, "reference_id"),
            query_id=_check_id(query_id, "query_id"),
            distance=self.result.distance,
            settings=self.settings,
        )


def align(
    reference: FrameFeatures,
    query: FrameFeatures,
    *,
    min_visible: int,
    band: float,
    step: str = "symmetricP1",
    weights: Mapping[str, float] | None = None,
) -> Alignment:
    """Align ``query`` with ``reference``: ``dtw(cost_matrix(reference, query, ...), band=band, step=step)``.

    ``reference`` and ``query``: ``FrameFeatures`` with the same units, version, ``min_scale_s`` and
    ``min_segment_length`` (positions in trunk lengths, angles as ``(sin, cos)``; a real clock each). ``min_visible``
    (an integer) and ``band`` (a fraction of the length in ``(0, 1]``) have no default; ``step`` is one of
    ``compare.dtw.STEPS`` (the product's ``symmetricP1`` by default); ``weights`` is ``None`` or a mapping of unit name
    to a finite weight of 0 or more (see ``cost_matrix``). Returns an ``Alignment``; no path is a result
    (``status="no_path"``), not an error. Runs no guard: the caller asks ``compare.guards.check_comparable`` first.
    ``CompareError`` naming the argument for anything the parts or the checks of the module cannot use; neither input is
    changed.
    """
    reference = _check_features(reference, "reference")
    query = _check_features(query, "query")
    minimums = _same_minimums(reference, query)
    cost = cost_matrix(reference, query, min_visible=min_visible, weights=weights)
    _check_clock(reference, "reference")
    _check_clock(query, "query")
    result = dtw(cost, band=band, step=step)
    settings = {
        "feature_version": str(cost.feature_version),
        "units": tuple(cost.units),
        "weights": tuple(float(w) for w in cost.weights),
        "min_visible": int(cost.min_visible),
        "band": float(result.params["band"]),  # type: ignore[arg-type]
        "step": str(result.params["step"]),
        **minimums,
    }
    return Alignment(reference, query, cost, result, MappingProxyType(settings))
