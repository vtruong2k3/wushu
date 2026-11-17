"""The quality layers of the pose (W6): the mask (P4.01), the Hampel outlier flag (P4.03), the short-gap bridges
(P4.02), the uniform grid for variable-frame-rate video (P4.04), the Butterworth low-pass (P4.05) and the left/right
swap flag (P4.06) now, the coverage in the next task.

Three layers stay apart (AGENTS.md section 5.3): ``raw`` (the target's keypoints as the model gave them, W5), ``mask``
(what is observed: a value is NaN with a reason, nothing is made up) and ``filtered``. The stages run in this order:
mask, Hampel, gaps, resampling, filter. Hampel (``filters.py``) only turns a cell into NaN with the reason ``outlier``;
the bridges of ``gaps`` are a flagged addition to that layer, never to the raw one: every bridged cell says so and
keeps the reason it was missing. ``resample.py`` puts the gap layer on a regular clock (the identity for a constant
frame rate): a grid time that is not a row holds flagged linear mixes, a pause in the timestamps is NaN with the reason
``no_frame``, and the map back to the real timestamps is kept. ``filters.py`` ends with the Butterworth low-pass, zero
phase, run by run on the grid layer: a run too short for it, or a clip too slow for it, keeps its values and is
flagged. ``lr_swap.py`` reads the mask layer beside Hampel and marks the pairs whose two labels jump onto each other's
place (a warning: no value or label is changed); its ``blocked`` mask is the input of the gap layer. Nothing in this
package changes the layer it reads.
"""

from __future__ import annotations


class QualityError(Exception):
    """A stage of the quality layer cannot go on: wrong parameters, or arrays of a wrong shape or type."""
