"""T-AUDIT-08: the performer of a chunk for the review: the most persistent large person (P3.08)."""

from __future__ import annotations

import numpy as np

from helpers.pose_raw_build import scene_from_paths
from helpers.track_build import FPS, stands
from taiji_ai.audit.analyse import target_track
from taiji_ai.track.state import TRACKED


def test_t_audit_08_a_chunk_that_opens_with_a_title_card_still_gets_the_performer():
    # a small "person" of the title card for the first 25 frames, then the performer (large) for the rest
    card = stands(1500.0, last=25)
    performer = stands(900.0, first=40)
    raw, ids = scene_from_paths({0: card, 1: performer}, n_frames=200, fps=FPS)

    track = target_track(raw)

    assert track is not None
    assert (ids[track.person_row[track.status == TRACKED]] == 1).all()  # only the performer is ever the target
    assert (track.status[:40] != TRACKED).all() and (track.status[40:] == TRACKED).all()


def test_t_audit_08_the_largest_mass_wins_over_the_first_person_and_over_a_short_large_one():
    # a long track beats a short one of the same size; a person present all the time beats a bystander for a few frames
    paths = {0: stands(900.0), 1: stands(1500.0, first=100, last=120)}
    raw, ids = scene_from_paths(paths, n_frames=200, fps=FPS)
    track = target_track(raw)
    assert track is not None and (ids[track.person_row[track.status == TRACKED]] == 0).all()
    assert int((track.status == TRACKED).sum()) == 200


def test_t_audit_08_nobody_or_only_weak_persons_gives_no_target():
    nobody, _ = scene_from_paths({0: lambda k: None}, n_frames=30, fps=FPS)
    assert target_track(nobody) is None
    weak, _ = scene_from_paths({0: stands(900.0, n_valid=3)}, n_frames=30, fps=FPS)  # too few keypoints to be followed
    assert target_track(weak) is None


def test_t_audit_08_the_performer_is_found_in_a_crowd_by_size_and_time():
    paths = {0: stands(300.0), 1: stands(1500.0), 2: stands(900.0)}  # same size: the first of the equal masses wins
    raw, _ = scene_from_paths(paths, n_frames=60, fps=FPS)
    track = target_track(raw)
    assert track is not None and bool(np.all(track.status == TRACKED))
