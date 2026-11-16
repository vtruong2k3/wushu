"""Measurement tools for the pose stage (P3.07): timing, GPU memory, comparison of two runs, the rule for N.

This package measures; it never changes a result. It is used by ``tools/bench_pose.py`` and may be reused by the worker
(P7) and by the benchmark of the target machine (P11.03).
"""

from __future__ import annotations


class BenchError(Exception):
    """A measurement cannot be made or an input of the measurement is wrong; the message says which and why."""
