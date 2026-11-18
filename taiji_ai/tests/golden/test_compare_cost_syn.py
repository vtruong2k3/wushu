"""T-CMP-02 on the generator: the masked cost of SYN-10 (a query that is the reference re-timed and under a similarity)
through the real chain (P6.02).

Every layer is what the pipeline would hand to the comparison: ``run_quality_arrays``, ``pose_filtered_from_result``,
then ``frame_features`` and ``cost_matrix`` (rows the query, columns the reference, ``min_visible`` 10 of 21 units).
SYN-10 samples one continuous pose function, so with ``k_start = k_end = 1`` the query is the reference on the same
clock under a scale and a shift (``scale_px`` 120: a scale of 1.7 does not fit the image at the default 200), and with a
warp ``t_query = W(t_ref)`` known in closed form (``truth["t_ref_of_query"]``).

Tolerances were measured before they were set (2026-11-17), noise-free unless said:

* ``k = 1``, scales 0.5, 0.8 and 1.7: the diagonal of the cost is at most 6.0e-6, 4.7e-6 and 1.9e-6 (every row; the
  trunk-normalised features carry no scale and no shift) and the whole matrix differs from the cost of the reference
  against itself by the same amounts. The bound is 1e-4.
* Away from the diagonal the cost grows: the median over the rows of the cost 5 rows from the diagonal is 0.0248 and
  20 rows 0.1099 (the bounds are 0.01 and 0.05); the matrix maximum is 0.394 (the bound is 0.2). **The matrix has a
  second valley along the anti-diagonal**: the action (raise then lower) is symmetric in time, so the pose at phase
  ``φ`` and at ``1 - φ`` are the same, and the cost there is at most 0.0185 (the bound is 0.03). That is the
  generator's action and not a defect of the cost; it is DTW's band and slope limits that choose between the two
  valleys (P6.03).
* ``k`` from 0.8 to 1.25 (123 query rows and 120 reference rows): the cost at the reference row nearest to the true
  correspondence of a query row is at most 0.0062 (the bound is 0.02: half a frame of a pose that moves 0.005 to 0.02
  per frame) and the row's minimum within 25 rows of the truth is 0.29 row from it in the median (the bound is 1; at the
  worst it is the mirror valley, 25.6 rows).
* 1 px of noise, scale 1.7, seeds 1 to 3 (the short-segment risk R1 of P6.01): the median of the diagonal is 0.0130 to
  0.0134 (the bound is 0.03). The diagonal at the 35 rows where the left forearm is shorter than 0.05 trunk lengths
  (2.4 px at this scale: its direction is arbitrary) has a median of 0.037 to 0.042 against 0.0105 to 0.0109 at the
  other rows, the largest value on the diagonal is 0.080 to 0.104, and without the two forearm angles (weight 0) it is
  at most 0.025 to 0.030. The cost does not decide what is too short (that is ``min_segment_length`` of
  ``frame_features``, or a weight): it shows the noise of a short segment, and the test says so. The cost 5 rows from
  the diagonal is 0.032 in the median and 20 rows 0.113 to 0.116 (bounds 0.02 and 0.08); 96 to 99 percent of the rows
  have their minimum within 3 rows of the diagonal or of the mirror valley (the bound is 90 percent).
"""

from __future__ import annotations

import numpy as np
import pytest

from helpers.metric_layers import layer_of_sequence
from helpers.synth import SynthPair, make_pair
from taiji_ai.compare.cost import CostMatrix, cost_matrix
from taiji_ai.compare.features import FrameFeatures, frame_features

SCALE_PX = 120.0
MIN_VISIBLE = 10  # of 21 units
DIAGONAL_TOL = 1e-4  # measured at most 6.0e-6
SIMILARITIES = [
    pytest.param(0.5, (40.0, -30.0), id="scale 0.5"),
    pytest.param(0.8, (-120.0, 60.0), id="scale 0.8"),
    pytest.param(1.7, (40.0, -30.0), id="scale 1.7"),
]


def syn10_cost(**params) -> tuple[SynthPair, FrameFeatures, FrameFeatures, CostMatrix]:
    """``(pair, reference features, query features, cost)`` of a SYN-10 pair through the real chain."""
    pair = make_pair("SYN-10", scale_px=SCALE_PX, **params)
    ref, qry = frame_features(layer_of_sequence(pair.ref)), frame_features(layer_of_sequence(pair.query))
    return pair, ref, qry, cost_matrix(ref, qry, min_visible=MIN_VISIBLE)


def offset_cost(v: np.ndarray, offset: int) -> np.ndarray:
    """The cost of every cell ``offset`` rows from the diagonal, on both sides (the matrix is square)."""
    idx = np.arange(len(v))
    return np.concatenate([v[idx[offset:], idx[offset:] - offset], v[idx[:-offset], idx[:-offset] + offset]])


@pytest.mark.parametrize(("query_scale", "shift"), SIMILARITIES)
def test_t_cmp_02_syn10_a_query_under_a_similarity_has_a_zero_diagonal_and_the_references_own_cost(query_scale, shift):
    _, ref, qry, cm = syn10_cost(
        seed=1, k_start=1.0, k_end=1.0, query_scale=query_scale, query_shift_px=shift, noise_px=0.0
    )
    v = cm.values
    assert v.shape == (120, 120) and np.isfinite(v).all() and (cm.n_common == 21).all()  # every unit of every frame
    assert np.abs(np.diagonal(v)).max() < DIAGONAL_TOL  # measured at most 6.0e-6: the same pose, any scale or shift
    own = cost_matrix(ref, ref, min_visible=MIN_VISIBLE).values
    assert (np.diagonal(own) == 0.0).all()
    assert np.abs(v - own).max() < DIAGONAL_TOL  # the query's scale and shift do not enter any cell
    assert v.max() > 0.2  # measured 0.394: the matrix is not trivially small
    assert cm.units == tuple(u.name for u in ref.units) and cm.weights == (1.0,) * 21 and cm.min_visible == MIN_VISIBLE


def test_t_cmp_02_syn10_the_cost_grows_away_from_the_diagonal_and_has_a_second_valley_on_the_anti_diagonal():
    _, _, _, cm = syn10_cost(
        seed=1, k_start=1.0, k_end=1.0, query_scale=0.8, query_shift_px=(-120.0, 60.0), noise_px=0.0
    )
    v = cm.values
    assert np.median(offset_cost(v, 5)) > 0.01 and np.median(offset_cost(v, 20)) > 0.05  # measured 0.0248 and 0.1099
    assert np.median(offset_cost(v, 20)) > 2.0 * np.median(offset_cost(v, 5))
    idx = np.arange(len(v))
    assert v[idx, len(v) - 1 - idx].max() < 0.03  # measured 0.0185: raise-then-lower is symmetric in time (the mirror)


@pytest.mark.parametrize(("query_scale", "shift"), [pytest.param(1.0, (0.0, 0.0), id="same size"), SIMILARITIES[1]])
def test_t_cmp_02_syn10_a_warped_query_has_its_valley_at_the_true_correspondence_rows_are_the_query(query_scale, shift):
    pair, ref, qry, cm = syn10_cost(
        seed=1, k_start=0.8, k_end=1.25, query_scale=query_scale, query_shift_px=shift, noise_px=0.0
    )
    v = cm.values
    assert len(qry.t_sec) == 123 and len(ref.t_sec) == 120 and v.shape == (123, 120)  # (query frames, reference frames)
    step = float(ref.t_sec[1] - ref.t_sec[0])
    k_true = np.asarray(pair.truth["t_ref_of_query"]) / step  # the reference row (a float) of every query row
    nearest = np.clip(np.rint(k_true).astype(int), 0, 119)
    assert v[np.arange(123), nearest].max() < 0.02  # measured 0.0062: half a frame of a moving pose
    deviation = []
    for i, k in enumerate(k_true):
        lo, hi = max(0, int(k) - 25), min(120, int(k) + 26)
        deviation.append(abs(lo + int(np.argmin(v[i, lo:hi])) - k))
    assert np.median(deviation) < 1.0  # measured 0.29 row: the row minimum sits on the true correspondence
    transposed = cost_matrix(qry, ref, min_visible=MIN_VISIBLE).values  # reference and query swapped: (120, 123)
    assert transposed.shape == (120, 123) and np.array_equal(transposed, v.T)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_t_cmp_02_syn10_at_one_pixel_of_noise_the_diagonal_stays_low_and_a_short_forearm_shows_its_noise(seed):
    pair, ref, qry, cm = syn10_cost(
        seed=seed, k_start=1.0, k_end=1.0, query_scale=1.7, query_shift_px=(40.0, -30.0), noise_px=1.0
    )
    v = cm.values
    diagonal = np.diagonal(v)
    assert np.isfinite(v).all() and np.median(diagonal) < 0.03  # measured 0.0130 to 0.0134
    kt = pair.ref.kp_true.astype(np.float64)
    trunk = np.linalg.norm((kt[:, 5] + kt[:, 6]) / 2 - (kt[:, 11] + kt[:, 12]) / 2, axis=1)
    forearm = np.linalg.norm(kt[:, 9] - kt[:, 7], axis=1) / trunk  # the left forearm in trunk lengths
    short = forearm < 0.05
    assert short.sum() >= 30  # the generator shrinks the forearm to 0.02 and back (35 rows)
    # R1 of P6.01: the direction of a segment of 2.4 px is arbitrary; the cost carries it (it decides nothing)
    assert np.median(diagonal[short]) > 0.02 and np.median(diagonal[~short]) < 0.02  # 0.037+ against 0.0109 at most
    assert np.median(diagonal[short]) > 2.0 * np.median(diagonal[~short])
    no_forearm = cost_matrix(ref, qry, min_visible=MIN_VISIBLE, weights={"l_forearm": 0.0, "r_forearm": 0.0})
    assert no_forearm.weights.count(0.0) == 2 and np.diagonal(no_forearm.values).max() < 0.06  # measured at most 0.030
    assert (np.diagonal(no_forearm.n_common) == 19).all()
    assert (
        np.median(offset_cost(v, 5)) > 0.02 and np.median(offset_cost(v, 20)) > 0.08
    )  # measured 0.032, 0.113 to 0.116
    idx = np.arange(len(v))
    near_valley = (np.abs(v.argmin(axis=1) - idx) <= 3) | (np.abs(v.argmin(axis=1) - (len(v) - 1 - idx)) <= 3)
    assert near_valley.mean() >= 0.9  # measured 0.958 to 0.992
