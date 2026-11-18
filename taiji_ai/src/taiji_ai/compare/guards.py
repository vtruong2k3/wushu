"""The guards of a comparison (W8, P6.05): may two segments be compared at all, and if not, every reason why.

W8 compares a segment with a reference segment "only when both have the same ``action``, ``side``, ``variant`` and
``view_category``, and the coverage of both is at least a threshold". ``check_comparable`` answers that before ``align``
runs. **A refusal is a result, not an error:** it is a ``GuardDecision`` with ``comparable=False`` and every reason, so
that the coach sees at once everything that is wrong; a description that is not a valid description (an action that does
not exist, a side the action does not have, ...) is a programming error and raises ``CompareError``.

**Segment description** (``SegmentInfo``, a plain description: the ``segment`` table is read by P8.06, not here):
``action`` an ontology id (``A01`` to ``A24``); ``side`` one of the sides of that action, the string ``"none"`` for a
movement without a side (never ``None``: the caller maps a nullable column); ``variant`` a short code of the form and of
the ontology version, such as ``taiji24/v0``: letters, digits, ``_``, ``.`` and ``-`` (1 to 64), optionally followed by
one ``/`` and a second such code, never a path or a name; ``view_category`` one of the ontology's views; ``flags`` a
``frozenset`` of the ontology flags that are set on the segment. Actions, sides, views and flags are checked against an
``Ontology`` (the shipped ``ontology_v0.yaml`` by default, read once per process; a made-up one may be passed). The
checks are written here and not taken from ``Ontology.check_segment``, whose messages echo the label it was given.

**Same action** means the same action *number* (``A07`` is not ``A08``, although both are "grasp the bird's tail"; a
technique that occurs under two numbers can start from another stance, so comparing across numbers is a decision for the
coach, later). The four comparisons ``action``, ``side``, ``variant``, ``view_category`` are independent of each other:
``A07`` left against ``A08`` right differs in both. A view ``unknown`` is **never** comparable, not even with another
``unknown``.

**Blocking flags** (``BLOCKING_FLAGS``): ``orientation_change`` and ``perspective_shift``. The shape of a movement in
the image plane is not the same movement when the person turns or when the depth changes, so a segment that carries
either flag is not compared. ``occlusion`` does not block: the masks of the features already leave the hidden joints
out (``compare.features``). A flag that is not in ``BLOCKING_FLAGS`` blocks nothing.

**Coverage** of a segment is the share, in ``[0, 1]``, of its rows (the rows of its ``FrameFeatures``, one per grid row)
in which at least ``min_visible`` units of the features are valid: the rows the masked cost can use (a cell of the cost
is ``+inf`` when fewer than ``min_visible`` units are valid in both frames). It is ``None`` for a segment without rows.
A coverage **equal to** ``min_coverage`` is enough (``coverage >= min_coverage``, on the two floats: ``7 / 10`` equals
``0.7``). ``min_visible`` (an integer from 1 to the number of units) and ``min_coverage`` (a number in ``(0, 1]``) have
no default (AGENTS.md section 5.5): the caller passes them and the decision echoes them. A ``min_visible`` above the
number of units of a feature set is a ``CompareError`` (as the cost refuses one above its weighted units): otherwise
every comparison would be refused for coverage because of a mistake in the settings. The units of the two segments are
not compared here (the cost refuses different units); each segment is counted on its own.

**Reasons**, a closed list, in this fixed order (all that apply are listed): ``action_differs``, ``side_differs``,
``variant_differs``, ``view_differs``, ``view_unknown`` (once, whichever segment or both has the view ``unknown``; with
``front`` against ``unknown`` the views also differ, so both are listed), then ``flagged_reference:<flag>`` for each
blocking flag of the reference and ``flagged_query:<flag>`` for each of the query (all of the reference first; inside
each, the order of ``BLOCKING_FLAGS``, never the order of the set), then ``no_rows_reference``, ``no_rows_query`` (a
segment without rows has no coverage, so it never also gets a ``coverage_low`` reason), then ``coverage_low_reference``,
``coverage_low_query``. ``comparable`` is true exactly when no reason applies.

Errors are ``CompareError`` naming the argument (``reference.side``, ``min_visible``, ...); a message shows a number or
a type, never a string given by the caller. Nothing given is changed; results are frozen dataclasses of plain values.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Final

import numpy as np

from taiji_ai.compare import CompareError
from taiji_ai.compare.features import FrameFeatures
from taiji_ai.schemas.ontology import Ontology, load_ontology

BLOCKING_FLAGS: Final[tuple[str, ...]] = ("orientation_change", "perspective_shift")  # not "occlusion": see above
UNKNOWN_VIEW: Final = "unknown"  # the view category that is never compared
_SHOWN_INTEGER_LIMIT: Final = 10**15  # an integer from here on is shown as a float, so a message stays short

# A form code, optionally followed by "/" and a version code, as in "taiji24/v0": short codes, never a path or a name.
_VARIANT: Final = re.compile(r"[A-Za-z0-9_.-]{1,64}(?:/[A-Za-z0-9_.-]{1,64})?")


@dataclass(frozen=True)
class SegmentInfo:
    """The description of one segment that a comparison depends on (checked against an ontology by the guard).

    ``action`` an ontology action id; ``side`` one of the action's sides (``"none"`` for no side, never ``None``);
    ``variant`` a short code such as ``taiji24/v0`` (the form and the ontology version); ``view_category`` an ontology
    view; ``flags`` a ``frozenset`` of the ontology flags set on the segment.
    """

    action: str
    side: str
    variant: str
    view_category: str
    flags: frozenset[str]


@dataclass(frozen=True)
class GuardDecision:
    """Whether two segments may be compared, and why not.

    ``comparable`` is true exactly when ``reasons`` is empty. ``reasons``: every reason that applies, in the fixed order
    of the module docstring. ``coverage_reference`` and ``coverage_query``: the share of rows (``[0, 1]``) with at least
    ``min_visible`` valid units, ``None`` for a segment without rows. ``min_visible`` and ``min_coverage``: the settings
    the decision was made with (echoed, never defaults).
    """

    comparable: bool
    reasons: tuple[str, ...]
    coverage_reference: float | None
    coverage_query: float | None
    min_visible: int
    min_coverage: float


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, (bool, np.bool_))


def _shown(value: Any) -> str:
    """A number as it is, anything else by its type: a message never echoes text the caller passed."""
    if not _is_number(value):
        return type(value).__name__
    if isinstance(value, (int, np.integer)):
        number = int(value)
        return repr(number) if abs(number) < _SHOWN_INTEGER_LIMIT else repr(_as_float(number))  # not 400 digits
    return repr(float(value))


def _as_float(value: Any) -> float:
    """``float(value)``, except that an integer beyond the range of a float is an infinity (BUG-0079), which every
    check below refuses, instead of an ``OverflowError``."""
    try:
        return float(value)
    except OverflowError:
        return math.inf if value > 0 else -math.inf


def _kind(value: Any) -> str:
    """How a refused field is named in a message: its type, or 'a string' (never the string itself)."""
    return "a string that is not accepted" if isinstance(value, str) else type(value).__name__


@lru_cache(maxsize=1)
def _default_ontology() -> Ontology:
    """The shipped ontology, read once per process (a frozen model: safe to share)."""
    return load_ontology()


def _check_min_visible(value: Any) -> int:
    if not isinstance(value, (int, np.integer)) or isinstance(value, (bool, np.bool_)) or value < 1:
        raise CompareError(f"min_visible must be an integer of at least 1, got {_shown(value)}")
    return int(value)


def _check_min_coverage(value: Any) -> float:
    if not _is_number(value) or not 0.0 < _as_float(value) <= 1.0:  # NaN and infinity fail the comparison
        raise CompareError(
            f"min_coverage must be a number in (0, 1], the least share of usable rows, got {_shown(value)}"
        )
    return _as_float(value)


def _check_ontology(ontology: Any) -> Ontology:
    if not isinstance(ontology, Ontology):
        raise CompareError(f"ontology must be an Ontology or None, got {type(ontology).__name__}")
    return ontology


def _check_info(info: Any, name: str, ontology: Ontology) -> None:
    """``CompareError`` naming ``name.<field>`` unless every field of ``info`` is valid in ``ontology``."""
    if not isinstance(info, SegmentInfo):
        raise CompareError(f"{name} must be a SegmentInfo, got {type(info).__name__}")
    action = next((a for a in ontology.actions if isinstance(info.action, str) and a.id == info.action), None)
    if action is None:
        ids = ", ".join(a.id for a in ontology.actions)
        raise CompareError(f"{name}.action must be an action id of the ontology ({ids}), got {_kind(info.action)}")
    if not isinstance(info.side, str) or info.side not in action.sides:
        raise CompareError(
            f"{name}.side must be one of the sides of action {action.id} ({', '.join(action.sides)}), "
            f"got {_kind(info.side)}"
        )
    if not isinstance(info.variant, str) or _VARIANT.fullmatch(info.variant) is None:
        raise CompareError(
            f"{name}.variant must be a short code of letters, digits, '_', '.' or '-' (1 to 64), optionally followed "
            f"by '/' and a second one (not a path or a name), got {_kind(info.variant)}"
        )
    if not isinstance(info.view_category, str) or info.view_category not in ontology.view_categories:
        raise CompareError(
            f"{name}.view_category must be one of the ontology views ({', '.join(ontology.view_categories)}), "
            f"got {_kind(info.view_category)}"
        )
    flags = ", ".join(ontology.flags)
    if not isinstance(info.flags, frozenset):
        raise CompareError(
            f"{name}.flags must be a frozenset of ontology flags ({flags}), got {type(info.flags).__name__}"
        )
    if any(not isinstance(flag, str) or flag not in ontology.flags for flag in info.flags):
        raise CompareError(f"{name}.flags must hold only ontology flags ({flags}), it holds a name that is not one")


def _check_valid(features: Any, name: str, min_visible: int) -> np.ndarray:
    """The ``valid`` array ``(N, U)`` of ``features``; ``CompareError`` if it is not a two-dimensional bool array or
    ``min_visible`` is above its ``U``."""
    if not isinstance(features, FrameFeatures):
        raise CompareError(f"{name} must be a FrameFeatures, got {type(features).__name__}")
    valid = features.valid
    if not isinstance(valid, np.ndarray) or valid.dtype != np.bool_ or valid.ndim != 2:
        described = (
            f"{valid.dtype} array of {valid.ndim} dimensions" if isinstance(valid, np.ndarray) else type(valid).__name__
        )
        raise CompareError(f"{name}.valid must be a two-dimensional bool array, got {described}")
    if min_visible > valid.shape[1]:
        raise CompareError(
            f"min_visible must not exceed the number of units of {name} ({valid.shape[1]}), got {min_visible}"
        )
    return valid


def _coverage(valid: np.ndarray, min_visible: int) -> float | None:
    """The share of rows of ``valid`` ``(N, U)`` with at least ``min_visible`` valid units; ``None`` for no rows."""
    rows = valid.shape[0]
    if rows == 0:
        return None
    usable = int(np.count_nonzero(np.count_nonzero(valid, axis=1) >= min_visible))
    return usable / rows


def check_comparable(
    reference: SegmentInfo,
    query: SegmentInfo,
    reference_features: FrameFeatures,
    query_features: FrameFeatures,
    *,
    min_visible: int,
    min_coverage: float,
    ontology: Ontology | None = None,
) -> GuardDecision:
    """Whether the segment ``query`` may be compared with the segment ``reference``, with every reason when not.

    ``reference`` and ``query`` describe the two segments (``SegmentInfo``); ``reference_features`` and
    ``query_features`` are their ``FrameFeatures`` (only ``valid`` is read). ``min_visible``: an integer from 1 to the
    number of units, the least valid units of a row for the row to count; ``min_coverage``: a number in ``(0, 1]``, the
    least share of counted rows; neither has a default. ``ontology``: the labels to check against (``None``: the shipped
    ontology). Returns a ``GuardDecision`` (the module docstring lists the reasons and their order); a refusal is a
    decision. Raises ``CompareError`` naming the argument for a description or a setting that is not valid.
    """
    visible = _check_min_visible(min_visible)
    least = _check_min_coverage(min_coverage)
    labels = _default_ontology() if ontology is None else _check_ontology(ontology)
    _check_info(reference, "reference", labels)
    _check_info(query, "query", labels)
    reference_valid = _check_valid(reference_features, "reference_features", visible)
    query_valid = _check_valid(query_features, "query_features", visible)
    coverage_reference = _coverage(reference_valid, visible)
    coverage_query = _coverage(query_valid, visible)

    reasons: list[str] = []
    if reference.action != query.action:
        reasons.append("action_differs")
    if reference.side != query.side:
        reasons.append("side_differs")
    if reference.variant != query.variant:
        reasons.append("variant_differs")
    if reference.view_category != query.view_category:
        reasons.append("view_differs")
    if UNKNOWN_VIEW in (reference.view_category, query.view_category):
        reasons.append("view_unknown")
    reasons.extend(f"flagged_reference:{flag}" for flag in BLOCKING_FLAGS if flag in reference.flags)
    reasons.extend(f"flagged_query:{flag}" for flag in BLOCKING_FLAGS if flag in query.flags)
    if coverage_reference is None:
        reasons.append("no_rows_reference")
    if coverage_query is None:
        reasons.append("no_rows_query")
    if coverage_reference is not None and coverage_reference < least:
        reasons.append("coverage_low_reference")
    if coverage_query is not None and coverage_query < least:
        reasons.append("coverage_low_query")
    return GuardDecision(
        comparable=not reasons,
        reasons=tuple(reasons),
        coverage_reference=coverage_reference,
        coverage_query=coverage_query,
        min_visible=visible,
        min_coverage=least,
    )
