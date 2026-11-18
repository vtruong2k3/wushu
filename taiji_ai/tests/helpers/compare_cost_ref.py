"""Hand-made frame features and an independent re-derivation of the masked cost (P6.02, Appendix C.2) for the tests of
``compare/cost.py``.

``make_features`` builds a ``FrameFeatures`` from arrays (no layer, no chain), so that a test can put any value, any
mask and any stored value under a mask. ``expected_cost`` is the cost of Appendix C.2 by plain Python loops over every
cell and every unit, with ``math`` only and never the module's own helpers: a cell is the weighted mean
``sum(w_u d_u) / sum(w_u)`` over the units with ``w_u > 0`` that are valid in both frames, ``d_u`` is the Euclidean norm
of the difference of the two stored 2-vectors for a position and, for an angle, the chord ``2 |sin((a - b) / 2)|`` of
the two angles that the stored ``(sin, cos)`` pairs give back through ``atan2``; the cell is ``+inf`` when fewer than
``min_visible`` units are common. Rows are the query, columns the reference.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

from helpers.compare_features_ref import TABLE
from taiji_ai.compare.features import FeatureUnit, FrameFeatures
from taiji_ai.pose.skeleton import IDX
from taiji_ai.schemas.quality_layers import DataSource

POSITIONS = ("LShoulder", "LWrist", "RWrist", "LKnee")
ANGLES = ("l_forearm", "trunk")
RECORDING_REF = "0b6f3c1e-5a2d-4f8e-9c3a-7d1e2b4a6c80"
RECORDING_QRY = "5d2f9a47-1c3b-4e60-8a7d-2b9e4c1f6a13"
SOURCES = (DataSource(dataset_id="D08", license="own recordings"),)


def make_units(positions: Sequence[str] = POSITIONS, angles: Sequence[str] = ANGLES) -> tuple[FeatureUnit, ...]:
    """The units, positions first and then angles, with the joint numbers of the real features."""
    return tuple(FeatureUnit("position", p, (IDX[p],)) for p in positions) + tuple(
        FeatureUnit("angle", a, (*TABLE[a][0], *TABLE[a][1])) for a in angles
    )


def make_features(
    values: np.ndarray,
    valid: np.ndarray,
    units: tuple[FeatureUnit, ...] | None = None,
    *,
    version: str = "1",
    recording_id: str = RECORDING_REF,
    frozen: bool = False,
) -> FrameFeatures:
    """A ``FrameFeatures`` of copies of ``values`` ``(N, U, 2)`` and ``valid`` ``(N, U)`` (the stored value under a
    false mask is whatever the caller put there). ``frozen`` makes the arrays read-only, as the real features are."""
    values = np.array(values, dtype=np.float64)
    valid = np.array(valid, dtype=bool)
    n, u = valid.shape
    arrays = {
        "t_sec": np.arange(n, dtype=np.float64) / 30.0,
        "values": values,
        "valid": valid,
        "reason": np.where(valid, 0, 1).astype(np.uint8),
        "bridged": np.zeros((n, u), dtype=bool),
    }
    if frozen:
        for a in arrays.values():
            a.setflags(write=False)
    return FrameFeatures(
        **arrays,
        units=make_units() if units is None else units,
        scale_px=100.0,
        scale_rows=n,
        scale_s=n / 30.0,
        roll_deg=0.0,
        step_s=1.0 / 30.0 if n > 1 else None,
        recording_id=recording_id,
        data_sources=SOURCES,
        version=version,
    )


def random_features(
    rng: np.random.Generator,
    n: int,
    *,
    units: tuple[FeatureUnit, ...] | None = None,
    p_invalid: float = 0.3,
    under_mask: float = float("nan"),
    recording_id: str = RECORDING_REF,
    frozen: bool = False,
) -> FrameFeatures:
    """``n`` rows of random features: a position is a normal 2-vector (trunk lengths), an angle the pair
    ``(sin φ, cos φ)`` of a random ``φ``; each cell is invalid with probability ``p_invalid`` and holds ``under_mask``
    in both components then (NaN, as the real features do)."""
    units = make_units() if units is None else units
    values = np.empty((n, len(units), 2))
    for u, unit in enumerate(units):
        if unit.kind == "position":
            values[:, u] = rng.normal(0.0, 1.0, size=(n, 2))
        else:
            phi = rng.uniform(-math.pi, math.pi, size=n)
            values[:, u] = np.stack([np.sin(phi), np.cos(phi)], axis=-1)
    valid = rng.random((n, len(units))) >= p_invalid
    values[~valid] = under_mask
    return make_features(values, valid, units, recording_id=recording_id, frozen=frozen)


def unit_weights(names: Sequence[str], weights: Mapping[str, float] | None) -> list[float]:
    """A weight per unit: the mapping's, and 1 for a unit that it does not name (every unit when ``None``)."""
    return [1.0 if weights is None or name not in weights else float(weights[name]) for name in names]


def chord(a: Sequence[float], b: Sequence[float]) -> float:
    """The distance of two angles given as ``(sin, cos)``: ``2 |sin((α - β) / 2)|`` from ``atan2`` of each pair."""
    delta = math.atan2(a[0], a[1]) - math.atan2(b[0], b[1])
    return 2.0 * abs(math.sin(delta / 2.0))


def expected_cost(
    reference: FrameFeatures,
    query: FrameFeatures,
    *,
    min_visible: int,
    weights: Mapping[str, float] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """``(cost (n, m) float64, n_common (n, m) int64)`` by plain loops; ``+inf`` below ``min_visible`` common units."""
    names = [u.name for u in reference.units]
    kinds = [u.kind for u in reference.units]
    w = unit_weights(names, weights)
    n, m = query.valid.shape[0], reference.valid.shape[0]
    cost = np.full((n, m), math.inf)
    counts = np.zeros((n, m), dtype=np.int64)
    for i in range(n):
        for k in range(m):
            numerator = denominator = 0.0
            count = 0
            for u, kind in enumerate(kinds):
                if w[u] <= 0.0 or not (bool(query.valid[i, u]) and bool(reference.valid[k, u])):
                    continue
                a, b = query.values[i, u].tolist(), reference.values[k, u].tolist()
                d = chord(a, b) if kind == "angle" else math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)
                numerator += w[u] * d
                denominator += w[u]
                count += 1
            counts[i, k] = count
            if count >= min_visible:
                cost[i, k] = numerator / denominator
    return cost, counts
