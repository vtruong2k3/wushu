"""The failure review of the pose on real footage (P3.08): the pass, the signals, the selection, the sheets, the labels.

Everything here looks at the pose; nothing changes it. Images and keypoint files of the videos stay on the local disk
(``data/reports/p3_08/``, ignored by git); the report holds numbers and IDs only.
"""

from __future__ import annotations


class AuditError(Exception):
    """The review cannot go on: a wrong input, a file that is not what it says, a review that is not valid."""
