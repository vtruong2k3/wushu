"""Structure check of one HALPE_26 skeleton: does the index mean what ``pose/skeleton.py`` says? (P3.01, T-POSE-04)

The check tests the *semantics of the index* on the output of the pose model, not the quality of the pose: on an
upright person the head is above the nose, the nose above the shoulders, and so on; the left and the right joints
are on opposite sides of the body and, for the pairs of the trunk and the legs that cannot cross, on the same side
of the image for all of them; the neck and the hip points are in the middle of the shoulders and of the hips; each
toe and heel is near the ankle of its own side.

Coordinates are image pixels, x to the right, y down (a smaller y is higher in the image). A check that cannot be
decided (a joint below the score limit, a missing value, a person who is not upright) is ``undecidable``, never
``pass``.

Limit: a global swap of every left and right label cannot be told from a person who turns his back, so the report
says on which side of the image the left joints are (``facing_side``) and only a frame where the face is seen decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

import numpy as np

from taiji_ai.pose.skeleton import IDX, NUM_JOINTS

Status = Literal["pass", "fail", "undecidable"]

# A joint under this score is not used (the pose model's own score, not a calibrated probability).
MIN_SCORE: Final = 0.3
# Shoulders to hips must go down by at least this share of the torso length (within about 60 degrees of vertical).
UPRIGHT_MIN_DY: Final = 0.5
# A pair votes on the side only if its two joints are at least this share of the torso apart in x.
SIDE_MIN_SEPARATION: Final = 0.10
# Fewer voting pairs than this cannot decide the side rule.
MIN_VOTING_PAIRS: Final = 3
# Neck and Hip are within this share of the torso length from the middle of the shoulders and of the hips.
CENTRE_MAX_DIST: Final = 0.35
# A toe or heel is within this share of the leg length (hip to ankle) from the ankle of its side.
FOOT_MAX_DIST: Final = 0.5
# "Closer to its own ankle" is decided only if the ankles are at least this share of the leg apart.
FOOT_MIN_ANKLE_SEPARATION: Final = 0.1

# Pairs that cannot cross in a stance: they must all lie the same way round on the image. The eyes and the ears are
# not here: the head turns independently of the body, and in a profile the model puts the hidden eye and ear on the
# other side (seen on a real frame in P3.01), so they must not vote.
_SIDE_PAIRS: Final[tuple[tuple[str, str], ...]] = (
    ("LShoulder", "RShoulder"), ("LHip", "RHip"), ("LKnee", "RKnee"), ("LAnkle", "RAnkle"),
    ("LBigToe", "RBigToe"), ("LSmallToe", "RSmallToe"), ("LHeel", "RHeel"),
)  # fmt: skip
_FOOT_POINTS: Final = {"L": ("LBigToe", "LSmallToe", "LHeel"), "R": ("RBigToe", "RSmallToe", "RHeel")}


@dataclass(frozen=True)
class OrderCheck:
    name: str
    status: Status
    detail: str


@dataclass(frozen=True)
class OrderReport:
    checks: tuple[OrderCheck, ...]
    facing_side: Literal["left_on_image_right", "left_on_image_left"] | None  # None unless the side rule passed

    @property
    def ok(self) -> bool:
        """True when no check failed (undecidable checks proved nothing, they did not fail)."""
        return all(c.status != "fail" for c in self.checks)


def check_joint_order(kp: np.ndarray, scores: np.ndarray, *, min_score: float = MIN_SCORE) -> OrderReport:
    """Check one skeleton ``kp`` (26, 2) pixels with ``scores`` (26,); see the module docstring."""
    kp = np.asarray(kp, dtype=np.float64)
    scores = np.asarray(scores, dtype=np.float64)
    if kp.shape != (NUM_JOINTS, 2):
        raise ValueError(f"keypoints must have shape ({NUM_JOINTS}, 2), got {kp.shape}")
    if scores.shape != (NUM_JOINTS,):
        raise ValueError(f"scores must have shape ({NUM_JOINTS},), got {scores.shape}")

    def have(*names: str) -> bool:
        idx = [IDX[n] for n in names]
        return bool(np.all(np.isfinite(kp[idx])) and np.all(scores[idx] >= min_score))

    def at(name: str) -> np.ndarray:
        return kp[IDX[name]]

    def mid(a: str, b: str) -> np.ndarray:
        return (at(a) + at(b)) / 2.0

    torso_names = ("LShoulder", "RShoulder", "LHip", "RHip")
    torso = 0.0
    upright = False
    if have(*torso_names):
        torso = float(np.linalg.norm(mid("LHip", "RHip") - mid("LShoulder", "RShoulder")))
        upright = (
            torso > 0 and float(mid("LHip", "RHip")[1] - mid("LShoulder", "RShoulder")[1]) >= UPRIGHT_MIN_DY * torso
        )

    checks = [
        _vertical_chain(have, at, mid, upright),
        _centre_points(have, at, mid, upright, torso),
    ]
    side_check, facing = _left_right_sides(have, at, torso)
    checks.append(side_check)
    checks.append(_feet_near_ankles(have, at))
    return OrderReport(tuple(checks), facing)


def _vertical_chain_names() -> tuple[str, ...]:
    return ("Head", "Nose", "LShoulder", "RShoulder", "LHip", "RHip", "LKnee", "RKnee", "LAnkle", "RAnkle")


def _vertical_chain(have, at, mid, upright: bool) -> OrderCheck:
    name = "vertical_chain"
    if not have(*_vertical_chain_names()):
        return OrderCheck(name, "undecidable", "a joint of the chain is missing or under the score limit")
    if not upright:
        return OrderCheck(name, "undecidable", "the person is not upright")
    ys = [
        at("Head")[1],
        at("Nose")[1],
        mid("LShoulder", "RShoulder")[1],
        mid("LHip", "RHip")[1],
        mid("LKnee", "RKnee")[1],
        mid("LAnkle", "RAnkle")[1],
    ]
    if all(a < b for a, b in zip(ys, ys[1:], strict=False)):
        return OrderCheck(
            name, "pass", "Head < Nose < shoulders < hips < knees < ankles (from the top of the image down)"
        )
    return OrderCheck(
        name, "fail", "y of Head, Nose, shoulders, hips, knees, ankles: " + ", ".join(f"{y:.0f}" for y in ys)
    )


def _centre_points(have, at, mid, upright: bool, torso: float) -> OrderCheck:
    name = "centre_points"
    if not have("Neck", "Hip", "LShoulder", "RShoulder", "LHip", "RHip"):
        return OrderCheck(name, "undecidable", "Neck, Hip, shoulders or hips missing or under the score limit")
    if not upright:
        return OrderCheck(name, "undecidable", "the person is not upright")
    d_neck = float(np.linalg.norm(at("Neck") - mid("LShoulder", "RShoulder"))) / torso
    d_hip = float(np.linalg.norm(at("Hip") - mid("LHip", "RHip"))) / torso
    detail = f"Neck {d_neck:.2f}, Hip {d_hip:.2f} of the torso from the middle of the shoulders and of the hips"
    return OrderCheck(name, "pass" if max(d_neck, d_hip) <= CENTRE_MAX_DIST else "fail", detail)


def _left_right_sides(
    have, at, torso: float
) -> tuple[OrderCheck, Literal["left_on_image_right", "left_on_image_left"] | None]:
    name = "left_right_sides"
    if torso <= 0:
        return OrderCheck(name, "undecidable", "no torso length (shoulders or hips missing)"), None
    votes: dict[str, int] = {}
    for left, right in _SIDE_PAIRS:
        if not have(left, right):
            continue
        dx = float(at(left)[0] - at(right)[0])
        if abs(dx) >= SIDE_MIN_SEPARATION * torso:
            votes[f"{left}/{right}"] = 1 if dx > 0 else -1
    if len(votes) < MIN_VOTING_PAIRS:
        return OrderCheck(
            name, "undecidable", f"only {len(votes)} pairs are far enough apart in x (need {MIN_VOTING_PAIRS})"
        ), None
    signs = set(votes.values())
    if len(signs) > 1:
        wrong = sorted(k for k, v in votes.items() if v != _majority(votes))
        return OrderCheck(name, "fail", "pairs on the other side than the majority: " + ", ".join(wrong)), None
    facing: Literal["left_on_image_right", "left_on_image_left"] = (
        "left_on_image_right" if signs == {1} else "left_on_image_left"
    )
    return OrderCheck(name, "pass", f"{len(votes)} pairs agree: {facing}"), facing


def _majority(votes: dict[str, int]) -> int:
    return 1 if sum(votes.values()) > 0 else -1


def _feet_near_ankles(have, at) -> OrderCheck:
    name = "feet_near_ankles"
    needed = ("LHip", "RHip", "LAnkle", "RAnkle", *_FOOT_POINTS["L"], *_FOOT_POINTS["R"])
    if not have(*needed):
        return OrderCheck(name, "undecidable", "a foot point, ankle or hip is missing or under the score limit")
    problems: list[str] = []
    worst = 0.0
    for side, other in (("L", "R"), ("R", "L")):
        ankle, other_ankle = at(f"{side}Ankle"), at(f"{other}Ankle")
        leg = float(np.linalg.norm(at(f"{side}Hip") - ankle))
        if leg <= 0:
            return OrderCheck(name, "undecidable", "no leg length")
        separated = float(np.linalg.norm(ankle - other_ankle)) >= FOOT_MIN_ANKLE_SEPARATION * leg
        for point in _FOOT_POINTS[side]:
            d_own = float(np.linalg.norm(at(point) - ankle))
            worst = max(worst, d_own / leg)
            if d_own > FOOT_MAX_DIST * leg:
                problems.append(f"{point} is {d_own / leg:.2f} of the leg from its ankle")
            elif separated and d_own >= float(np.linalg.norm(at(point) - other_ankle)):
                problems.append(f"{point} is closer to the other ankle")
    if problems:
        return OrderCheck(name, "fail", "; ".join(problems))
    return OrderCheck(name, "pass", f"toes and heels within {worst:.2f} of the leg from their own ankle")
