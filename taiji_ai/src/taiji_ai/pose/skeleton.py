"""HALPE_26 skeleton definition (schema ``halpe26/1``).

Index order follows the HALPE-26 / RTMPose body7-halpe26 output. Verified on real model output on 2026-11-16
(P3.01, ``Docs/reports/p3_01_joint_order.md``): ``halpe26/1`` is confirmed; bump the version if anything changes.
Note: Sports2D/Pose2Sim export columns in tree order, not in this index order.
"""

from __future__ import annotations

from typing import Final

SKELETON_ID: Final = "halpe26/1"

JOINTS: Final[tuple[str, ...]] = (
    "Nose", "LEye", "REye", "LEar", "REar",
    "LShoulder", "RShoulder", "LElbow", "RElbow", "LWrist", "RWrist",
    "LHip", "RHip", "LKnee", "RKnee", "LAnkle", "RAnkle",
    "Head", "Neck", "Hip",
    "LBigToe", "RBigToe", "LSmallToe", "RSmallToe", "LHeel", "RHeel",
)  # fmt: skip
NUM_JOINTS: Final = len(JOINTS)
IDX: Final[dict[str, int]] = {name: i for i, name in enumerate(JOINTS)}

LR_PAIRS: Final[tuple[tuple[int, int], ...]] = (
    (1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12),
    (13, 14), (15, 16), (20, 21), (22, 23), (24, 25),
)  # fmt: skip

# Joints that must be visible for a frame to count as valid (v3 / TECH_WORKFLOW W6).
ESSENTIAL: Final[tuple[int, ...]] = (5, 6, 11, 12, 13, 14, 15, 16, 24, 25)

# Joint groups used by the tempo metric (Appendix B3).
GROUPS: Final[dict[str, tuple[int, ...]]] = {
    "hands": (9, 10),
    "hips": (11, 12),
    "feet": (15, 16, 24, 25),
}

# Ground-reference candidates for hip-height variant B (lowest point in the image).
GROUND_CANDIDATES: Final[tuple[int, ...]] = (15, 16, 24, 25)

# Limb edges for drawing / segment angles.
EDGES: Final[tuple[tuple[int, int], ...]] = (
    (17, 18), (18, 19),                       # head-neck-hip (model's own centre line)
    (5, 7), (7, 9), (6, 8), (8, 10),          # arms
    (5, 6), (11, 12), (5, 11), (6, 12),       # torso box
    (11, 13), (13, 15), (12, 14), (14, 16),   # legs
    (15, 24), (15, 20), (20, 22),             # left foot
    (16, 25), (16, 21), (21, 23),             # right foot
)  # fmt: skip


def mirror_index() -> tuple[int, ...]:
    """Index permutation that swaps left/right joints (for explicit, coach-requested mirroring)."""
    perm = list(range(NUM_JOINTS))
    for a, b in LR_PAIRS:
        perm[a], perm[b] = b, a
    return tuple(perm)
