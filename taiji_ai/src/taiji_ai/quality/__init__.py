"""The quality layers of the pose (W6): the mask (P4.01), the Hampel outlier flag (P4.03) and the short-gap bridges
(P4.02) now, resampling, the Butterworth filter and the coverage in the next tasks.

Three layers stay apart (AGENTS.md section 5.3): ``raw`` (the target's keypoints as the model gave them, W5), ``mask``
(what is observed: a value is NaN with a reason, nothing is made up) and ``filtered``. The stages run in this order:
mask, Hampel, gaps, resampling, filter. Hampel (``filters.py``) only turns a cell into NaN with the reason ``outlier``;
the bridges of ``gaps`` are a flagged addition to that layer, never to the raw one: every bridged cell says so and
keeps the reason it was missing. Nothing in this package changes the layer it reads.
"""

from __future__ import annotations


class QualityError(Exception):
    """A stage of the quality layer cannot go on: wrong parameters, or arrays of a wrong shape or type."""
