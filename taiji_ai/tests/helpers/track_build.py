"""Small scenes for the P3.06 tests: explicit people on explicit paths, no video and no model.

``stands`` makes the path of one person (a box of fixed size, absent in some frames); ``resolve`` runs the three steps
of W5 (association, target choice, target over time) on a scene and returns everything a test may look at.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from helpers.pose_raw_build import box, scene_from_paths
from taiji_ai.pose.runner import PoseRaw
from taiji_ai.track.associate import Tracks, associate_tracks
from taiji_ai.track.state import TargetStateParams, TargetTrack, resolve_target
from taiji_ai.track.target import TargetSelection, select_target

FPS = 30.0
BOX_W, BOX_H, BOX_CY = 200.0, 500.0, 600.0
HOME_X = 900.0


def person_box(cx: float) -> tuple[float, float, float, float]:
    return box(cx, BOX_CY, BOX_W, BOX_H)


def stands(
    x: float,
    *,
    absent: Sequence[tuple[int, int]] = (),
    first: int = 0,
    last: int | None = None,
    n_valid: int = 26,
) -> Callable[[int], tuple[tuple[float, float, float, float], int] | None]:
    """A person standing at ``x`` from frame ``first`` to ``last`` (exclusive), absent in the ranges ``absent``."""

    def path(k: int):
        if k < first or (last is not None and k >= last):
            return None
        if any(a <= k < b for a, b in absent):
            return None
        return person_box(x), n_valid

    return path


def walks(x0: float, x1: float, k0: int, k1: int, *, first: int = 0):
    """A person at ``x0`` until frame ``k0``, then walking at a constant speed to ``x1`` at ``k1``, then standing."""

    def path(k: int):
        if k < first:
            return None
        frac = min(1.0, max(0.0, (k - k0) / (k1 - k0)))
        return person_box(x0 + frac * (x1 - x0)), 26

    return path


@dataclass
class Run:
    raw: PoseRaw
    ids: np.ndarray  # true identity of every person row
    tracks: Tracks
    selection: TargetSelection
    target: TargetTrack

    def identities_of_tracked(self) -> np.ndarray:
        """True identity of the person used in every ``tracked`` frame."""
        rows = self.target.person_row[self.target.status == 0]
        return self.ids[rows]


def resolve(
    paths: dict,
    n_frames: int,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    at_t_sec: float | None = None,
    params: TargetStateParams | None = None,
    **scene_kwargs,
) -> Run:
    """Association, default or user-box target choice and ``resolve_target`` on a scene of explicit paths.

    ``bbox`` defaults to the performer's home box (identity 0 standing at ``HOME_X``).
    """
    raw, ids = scene_from_paths(paths, n_frames=n_frames, fps=FPS, **scene_kwargs)
    tracks = associate_tracks(raw)
    selection = select_target(raw, bbox=bbox or person_box(HOME_X), at_t_sec=at_t_sec)
    return Run(raw, ids, tracks, selection, resolve_target(raw, tracks, selection, params=params))
