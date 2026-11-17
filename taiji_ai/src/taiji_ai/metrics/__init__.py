"""The metrics of W7 (P5): hip height, trunk lean and tempo, and the types that carry their results.

``series.py`` (P5.01) holds ``MetricSeries``: the rows of one metric with the reason why a row has no value, from which
the valid intervals and the coverage are derived and checked; the models of the summary are in
``taiji_ai.schemas.metric``. A metric computes in image pixels (y down) on the final layer of the quality stage
(``pose_filtered.npz``) and never fills a value: a row that cannot be measured is NaN with a reason.
"""

from __future__ import annotations


class MetricError(Exception):
    """A metric result cannot be built or is inconsistent: wrong arrays, a header that disagrees with its rows."""
