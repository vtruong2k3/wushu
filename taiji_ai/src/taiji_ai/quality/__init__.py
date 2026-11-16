"""The quality layers of the pose (W6): the mask now (P4.01), the gaps, the filters and the coverage in the next tasks.

Three layers stay apart (AGENTS.md section 5.3): ``raw`` (the target's keypoints as the model gave them, W5), ``mask``
(what is observed: a value is NaN with a reason, nothing is made up) and ``filtered``. Nothing in this package changes
the layer it reads.
"""

from __future__ import annotations


class QualityError(Exception):
    """A stage of the quality layer cannot go on: wrong parameters, or arrays of a wrong shape or type."""
