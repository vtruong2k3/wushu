"""T-MET-11e: every metric echoes the cut-off that was applied to its layer (P5.09).

DEC-0061: the threshold of a pause, the minimum duration and the Butterworth cut-off are one triple, because the same
movement has a different paused share at 4, 6 and 8 Hz. A record can only bind the cut-off if the summary says which one
the result was computed on. The echo is ``filter_cutoff_hz`` in ``parameters``: the design cut-off of the layer when the
filter could be designed (it is below half the sampling rate), ``None`` when the filter was skipped.

The echo must be what the layer really did, so each case also looks at ``layer.filtered`` (written by the filter
stage), and it must not touch a value: two layers with the same arrays and a different cut-off in the header give the
same series.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from helpers.metric_runs import ALL_NAMES, layer_at, run_all, with_cutoff
from taiji_ai.metrics import MetricError
from taiji_ai.metrics.rows import assemble_series, segment_rows

KEY = "filter_cutoff_hz"


def test_t_met_11e_the_seven_metrics_are_the_ones_run_and_each_echoes_the_default_cutoff():
    results = run_all(layer_at(6.0))
    assert sorted(results) == sorted(ALL_NAMES) and len(results) == 7
    for name, result in results.items():
        assert result.summary.parameters[KEY] == 6.0, name
        assert result.series.header.parameters[KEY] == 6.0, name


@pytest.mark.parametrize("cutoff", [1.0, 4.0, 6.0, 8.0, 14.99])
def test_t_met_11e_a_cutoff_below_nyquist_is_echoed_and_the_layer_was_really_filtered(cutoff):
    layer = layer_at(cutoff)
    assert layer.filtered.any()  # the filter stage did its work at this cut-off
    for name, result in run_all(layer).items():
        assert result.summary.parameters[KEY] == cutoff, name


@pytest.mark.parametrize("cutoff", [15.0, 15.01, 20.0, 1000.0])
def test_t_met_11e_a_cutoff_that_cannot_be_designed_is_echoed_as_none_and_the_layer_was_not_filtered(cutoff):
    layer = layer_at(cutoff)  # 30 fps: Nyquist is 15 Hz and a cut-off at it is not below it
    assert not layer.filtered.any()
    for name, result in run_all(layer).items():
        assert result.summary.parameters[KEY] is None, name
        assert result.series.header.parameters[KEY] is None, name


@pytest.mark.parametrize(("cutoff", "echoed"), [(15.999, 15.999), (16.0, None), (16.001, None)])
def test_t_met_11e_a_cutoff_exactly_at_half_the_rate_is_not_below_it(cutoff, echoed):
    layer = layer_at(cutoff, fps=32.0)  # 1/32 s is exact in binary: the rate is 32.0 and half of it is exactly 16.0
    assert layer.meta.timeline.sampling_hz == 32.0
    assert bool(layer.filtered.any()) is (echoed is not None)  # the filter stage drew the same line
    for name, result in run_all(layer).items():
        assert result.summary.parameters[KEY] == echoed, name


def test_t_met_11e_the_default_cutoff_on_a_slow_camera_is_above_nyquist_and_none():
    layer = layer_at(6.0, fps=10.0, n=40)  # 10 fps: Nyquist 5 Hz
    assert not layer.filtered.any()
    assert all(r.summary.parameters[KEY] is None for r in run_all(layer).values())


def test_t_met_11e_a_layer_of_one_row_has_no_rate_and_no_cutoff_to_echo():
    layer = layer_at(6.0, n=1)
    assert layer.meta.timeline.sampling_hz is None
    for name, result in run_all(layer).items():
        assert result.summary.parameters[KEY] is None, name


def test_t_met_11e_the_echo_changes_no_value_only_the_one_key():
    base = layer_at(6.0)
    other = with_cutoff(base, 8.0)  # the same arrays, a different cut-off in the header
    a, b = run_all(base), run_all(other)
    for name in ALL_NAMES:
        sa, sb = a[name].series, b[name].series
        assert np.array_equal(sa.values, sb.values, equal_nan=True), name
        assert np.array_equal(sa.reason, sb.reason) and np.array_equal(sa.t_sec, sb.t_sec), name
        assert a[name].summary.statistics == b[name].summary.statistics, name
        assert a[name].summary.events == b[name].summary.events, name
        assert sa.header.coverage == sb.header.coverage and sa.header.valid_intervals == sb.header.valid_intervals
        assert sa.header.missing_by_reason == sb.header.missing_by_reason, name
        pa, pb = dict(a[name].summary.parameters), dict(b[name].summary.parameters)
        assert (pa.pop(KEY), pb.pop(KEY)) == (6.0, 8.0) and pa == pb, name


def test_t_met_11e_the_summary_is_valid_json_with_the_echo_as_a_number_or_null():
    for cutoff, expected in ((6.0, 6.0), (1000.0, None)):
        for result in run_all(layer_at(cutoff)).values():
            assert json.loads(result.summary.model_dump_json())["parameters"][KEY] == expected


def test_t_met_11e_a_metric_cannot_overwrite_the_echo_with_its_own_value():
    layer = layer_at(6.0)
    rows = segment_rows(layer)
    reason = np.zeros(len(rows.t_sec), dtype=np.uint8)
    values = np.ones(len(rows.t_sec))
    args = {
        "metric_name": "hip_height_b",
        "metric_version": "1",
        "units": "body_lengths",
        "min_valid_s": None,
        "camera_id": "camA",
        "view_category": "front",
    }
    ok = assemble_series(rows, reason, values, parameters={"a": 1}, **args)
    assert ok.header.parameters == {"a": 1, KEY: 6.0}
    with pytest.raises(MetricError, match=KEY):
        assemble_series(rows, reason, values, parameters={KEY: 3.0}, **args)
