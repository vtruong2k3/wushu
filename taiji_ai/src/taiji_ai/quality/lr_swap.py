"""The left/right swap flag (W6, P4.06): a pair whose two labels jump onto each other's place is marked, and nothing is
corrected.

The pose model sometimes gives the label ``left`` to the right limb and the reverse (the ``lr_swap`` of P3.08: legs and
feet in side lunges, the labels flipping between frames 0.3 s apart). The score does not warn, and Hampel does not see a
swap that lasts. ``detect_lr_swaps`` reads the **mask layer** (observed cells, before Hampel) and looks at every pair of
``LR_PAIRS`` at every row for a **crossed jump**; it returns a warning and **changes no value**: to swap the labels back
would change what a measurement means (AGENTS.md section 5.1). The mask ``blocked`` is the input of the gap layer ("do
not bridge across a suspected turning point", W6, ``interpolate_gaps(blocked=...)``) and the table of events feeds the
warnings of the report. The decisions are DEC-0049.

The rules, in this order (every distance is in torso lengths):

1. **The scale.** The torso is ``torso_px`` or the median torso of the layer (``filters.torso_length_px``: the distance
   between the middle of the shoulders and the middle of the hips over the rows with the four joints observed). Without
   a torso there is no event (``torso_px`` is NaN in the result).
2. **The event.** A pair ``(a, b)`` has an event at row ``t`` (``t >= 1``) if the cells ``a`` and ``b`` are observed at
   the rows ``t-1`` and ``t``, the two rows are at most ``max_dt_s`` apart (+1e-9 s, real timestamps), and with
   ``stay_a`` = the distance of ``a`` between the two rows, ``stay_b`` likewise for ``b``, ``cross_a`` = the distance
   from ``a`` at ``t`` to ``b`` at ``t-1`` and ``cross_b`` = the distance from ``b`` at ``t`` to ``a`` at ``t-1``: both
   labels moved at least ``min_jump`` (``stay_a >= min_jump`` and ``stay_b >= min_jump``) and each landed within
   ``max_cross_ratio`` of its own move of the **other** label's previous place (``cross_a <= max_cross_ratio x stay_a``
   and likewise for b). The limits are inclusive. A limb that moves fast alone, two limbs that cross smoothly (no jump),
   a label that jumps alone (a flicker: Hampel's) and two labels that jump to somewhere else are not events. A swap of
   two joints that are closer together than ``min_jump`` has no event and changes no position by more than that: it is
   not seen, and nothing is flagged.
3. **Pairing.** The events of one pair, in time order, are taken greedily: an event is the **enter** of a swap if the
   next event of the same pair is at most ``max_swap_s`` later (+1e-9 s); that one is its **exit**, and both are
   consumed. An event without a partner is **unpaired**. The rows from the enter (inclusive) to the exit (exclusive) are
   the swapped rows: ``suspect`` is True for the **two joints of the pair** in those rows. An unpaired event marks no
   interval.
4. **The rows of the events are marked too.** ``events`` is True at every event row for the pair; ``blocked`` is
   ``suspect`` plus the two joints of every event row (the jump itself is a row at which the labels are not to be
   trusted; the exit row is in it although the labels there are right again). ``frame_suspect`` is the rows with a
   ``suspect`` cell.
5. **Nothing is changed or filled.** A cell that is not observed is never part of an event, so a swap across a hole is
   not seen.

The state of a swap is not observed, only its jumps: with one jump alone (the swap lasts, or the other jump was missed)
the length is unknown, and a jump that is missed or invented turns the pairing of the rest of a chain around. ``events``
and ``blocked`` mark every jump in any case. A swap of every label of the body cannot be told from a person who turns
his back (``pose/order_check.py``).

Units and coordinates: positions are pixels of the upright image, x right, y down; times are seconds from the stream
start (real PTS). Inputs are not changed; the result arrays are new and read-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

from taiji_ai.pose.skeleton import LR_PAIRS, NUM_JOINTS
from taiji_ai.quality import QualityError
from taiji_ai.quality._checks import check_layer, frozen, is_int, is_real
from taiji_ai.quality.filters import torso_length_px
from taiji_ai.quality.mask import MaskedTrack

ENTER: Final = 0
EXIT: Final = 1
UNPAIRED: Final = 2
EVENT_OUTCOME_NAMES: Final = ("enter", "exit", "unpaired")  # the index is the code

_EPS_S: Final = 1e-9  # a limit of 0.25 s is not an exact float: the boundary must not depend on it


@dataclass(frozen=True)
class SwapParams:
    """The parameters of the swap flag: sensitivity parameters of a warning, proposals measured on D20 (DEC-0049).
    Wrong values raise ``QualityError``."""

    # [torso] finite and above 0: both labels move at least this far
    min_jump: float = 0.2
    # in (0, 1]: each lands within this share of its own move of the other label's previous place
    max_cross_ratio: float = 0.5
    # [s] finite and above 0: the two rows are at most this far apart
    max_dt_s: float = 0.25
    # [s] finite and above 0: an event is paired with the next one of its pair within this time
    max_swap_s: float = 0.5
    # distinct joints in [0, 25]; a joint is in at most one pair
    pairs: tuple[tuple[int, int], ...] = LR_PAIRS

    def __post_init__(self) -> None:
        jump = self.min_jump
        if not (is_real(jump) and np.isfinite(jump) and jump > 0.0):
            raise QualityError(f"min_jump must be a finite number of torso lengths above 0, got {jump!r}")
        ratio = self.max_cross_ratio
        if not (is_real(ratio) and 0.0 < ratio <= 1.0):  # a comparison with NaN is False: NaN is refused too
            raise QualityError(f"max_cross_ratio must be a number in (0, 1], got {ratio!r}")
        for name in ("max_dt_s", "max_swap_s"):
            value = getattr(self, name)
            if not (is_real(value) and np.isfinite(value) and value > 0.0):
                raise QualityError(f"{name} must be a finite number of seconds above 0, got {value!r}")
        try:
            pairs = tuple(tuple(pair) for pair in self.pairs)
        except TypeError as exc:
            raise QualityError(f"pairs must be a sequence of pairs of joint indices, got {self.pairs!r}") from exc
        flat = [joint for pair in pairs for joint in pair]
        if (
            not pairs
            or any(len(pair) != 2 for pair in pairs)
            or not all(is_int(joint) and 0 <= joint < NUM_JOINTS for joint in flat)
            or len(set(flat)) != len(flat)
        ):
            raise QualityError(
                f"pairs must be a non-empty sequence of pairs of distinct joint indices in [0, {NUM_JOINTS - 1}], "
                f"no joint in two pairs, got {self.pairs!r}"
            )
        object.__setattr__(self, "min_jump", float(jump))
        object.__setattr__(self, "max_cross_ratio", float(ratio))
        object.__setattr__(self, "max_dt_s", float(self.max_dt_s))
        object.__setattr__(self, "max_swap_s", float(self.max_swap_s))
        object.__setattr__(self, "pairs", tuple((int(a), int(b)) for a, b in pairs))


@dataclass(frozen=True, eq=False)
class EventTable:
    """One row per event, ordered by pair and then by row; every array is new and read-only (``E`` rows)."""

    pair: np.ndarray  # (E,) int16; index in ``SwapParams.pairs``
    row: np.ndarray  # (E,) int32; the row of the jump (the first row after it)
    t_s: np.ndarray  # (E,) float64 [s]; the time of that row
    jump: np.ndarray  # (E,) float32 [torso]; the smaller of the two moves
    outcome: np.ndarray  # (E,) uint8; index into ``EVENT_OUTCOME_NAMES``

    def __len__(self) -> int:
        return int(self.pair.shape[0])


@dataclass(frozen=True, eq=False)
class SwapResult:
    """The swap flag of ``T`` rows; every array is new and read-only (``T`` may be 0). No value of the input."""

    events: np.ndarray  # (T, P) bool; the pair jumped at this row (P = number of pairs)
    suspect: np.ndarray  # (T, 26) bool; the two joints of a pair in the rows from an enter to its exit
    table: EventTable
    torso_px: float  # [px] the scale used; NaN when it could not be measured
    params: SwapParams

    @property
    def blocked(self) -> np.ndarray:
        """``(T, 26)`` bool: ``suspect`` plus the two joints of every event row (``interpolate_gaps(blocked=...)``)."""
        out = np.array(self.suspect, copy=True)
        for p, (a, b) in enumerate(self.params.pairs):
            out[:, a] |= self.events[:, p]
            out[:, b] |= self.events[:, p]
        return frozen(out)

    @property
    def frame_suspect(self) -> np.ndarray:
        """``(T,)`` bool: the rows in which a pair is thought to be swapped (a ``suspect`` cell)."""
        return frozen(self.suspect.any(axis=1))


def _scale(torso_px: float | None, keypoints: np.ndarray, reason: np.ndarray) -> float:
    if torso_px is None:
        return torso_length_px(keypoints, reason)
    if not (is_real(torso_px) and np.isfinite(torso_px) and torso_px > 0.0):
        raise QualityError(f"torso_px must be a finite number of pixels above 0, got {torso_px!r}")
    return float(torso_px)


def detect_lr_swaps(
    keypoints: np.ndarray,
    reason: np.ndarray,
    t_sec: np.ndarray,
    params: SwapParams | None = None,
    *,
    torso_px: float | None = None,
) -> SwapResult:
    """Flag the left/right swaps of a mask layer; see the module docstring for the rules.

    ``keypoints`` ``(T, 26, 2)`` float (pixels) with NaN exactly where ``reason`` (``(T, 26)`` uint8, the codes of
    ``quality/mask.py``) is not ``ok``; ``t_sec`` ``(T,)`` float seconds, finite and strictly increasing; ``torso_px``
    the scale in pixels (``None``: the median torso of the layer). The inputs are not changed. Raises ``QualityError``
    for anything else.
    """
    params = SwapParams() if params is None else params
    kp, rs, t = check_layer(keypoints, reason, t_sec)
    scale = _scale(torso_px, kp, rs)
    n = kp.shape[0]
    pairs = params.pairs
    events = np.zeros((n, len(pairs)), dtype=bool)
    jump = np.full((n, len(pairs)), np.nan)
    if n >= 2 and np.isfinite(scale):
        values = kp.astype(np.float64)
        near = np.diff(t) <= params.max_dt_s + _EPS_S
        limit = params.min_jump * scale
        for p, (a, b) in enumerate(pairs):
            stay_a = np.linalg.norm(values[1:, a] - values[:-1, a], axis=-1)
            stay_b = np.linalg.norm(values[1:, b] - values[:-1, b], axis=-1)
            cross_a = np.linalg.norm(values[1:, a] - values[:-1, b], axis=-1)
            cross_b = np.linalg.norm(values[1:, b] - values[:-1, a], axis=-1)
            # a cell that is not observed is NaN (the contract of a layer): every comparison with it is False, so it is
            # never part of an event
            with np.errstate(invalid="ignore"):
                hit = (
                    near
                    & (stay_a >= limit)
                    & (stay_b >= limit)
                    & (cross_a <= params.max_cross_ratio * stay_a)
                    & (cross_b <= params.max_cross_ratio * stay_b)
                )
            events[1:, p] = hit
            jump[1:, p] = np.where(hit, np.minimum(stay_a, stay_b) / scale, np.nan)
    suspect = np.zeros((n, NUM_JOINTS), dtype=bool)
    pair_of, row_of, outcome_of = [], [], []
    for p, (a, b) in enumerate(pairs):
        rows = np.flatnonzero(events[:, p])
        i = 0
        while i < len(rows):
            if i + 1 < len(rows) and t[rows[i + 1]] - t[rows[i]] <= params.max_swap_s + _EPS_S:
                suspect[rows[i] : rows[i + 1], a] = True
                suspect[rows[i] : rows[i + 1], b] = True
                pair_of += [p, p]
                row_of += [int(rows[i]), int(rows[i + 1])]
                outcome_of += [ENTER, EXIT]
                i += 2
            else:
                pair_of.append(p)
                row_of.append(int(rows[i]))
                outcome_of.append(UNPAIRED)
                i += 1
    row_index = np.array(row_of, dtype=np.int64)
    table = EventTable(
        pair=frozen(np.array(pair_of, dtype=np.int16)),
        row=frozen(row_index.astype(np.int32)),
        t_s=frozen(t[row_index].astype(np.float64)),
        jump=frozen(jump[row_index, np.array(pair_of, dtype=np.int64)].astype(np.float32)),
        outcome=frozen(np.array(outcome_of, dtype=np.uint8)),
    )
    return SwapResult(events=frozen(events), suspect=frozen(suspect), table=table, torso_px=float(scale), params=params)


def detect_lr_swaps_track(
    masked: MaskedTrack, params: SwapParams | None = None, *, torso_px: float | None = None
) -> SwapResult:
    """The swap flag of a masked ``TargetTrack``: its keypoints, reasons and real timestamps, margins included.

    The frames that are not the target's are ``not_tracked`` in the mask: their cells are not observed, never judged.
    """
    return detect_lr_swaps(masked.mask.keypoints, masked.mask.reason, masked.t_sec, params, torso_px=torso_px)
