"""The comparison of a segment with a reference (W8, Phase 6): frame features, the masked cost, constrained DTW, the
local tempo along the path, the guards and the "normal band" of the coach's own takes.

Shape is compared with DTW; **tempo is always reported on the original time axes** (``FrameFeatures.t_sec`` is the real
clock of the final layer, never a row index). The parameters that decide what is compared (``min_visible``, the band,
the coverage minimum, the smoothing window) have no default: the caller passes them and every result echoes them
(AGENTS.md section 5.5). Positions are in trunk lengths, angles are ``(sin, cos)`` pairs, and a value that could not be
computed is NaN with a reason, never 0 (section 5.1). The shared contracts of the modules are written in
``Docs/tasks/P6_overview.md``.
"""

from __future__ import annotations


class CompareError(Exception):
    """A comparison step is given something it cannot use (wrong shape, NaN, a refused argument); the message names the
    argument and never echoes free text. A comparison that is not possible for a *reason of the data* (a guard, no path)
    is a result, not this error."""
