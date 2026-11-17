"""Kinect-format text for the P4.08 tests: made here, never read from the dataset (AGENTS.md 9.4.7).

A row is ``timestamp [ms]`` then 25 joints x ``x y z`` [mm], 76 numbers, in the order of the Kinect V2 ``JointType``
(listed here on its own, not taken from the module under test). ``skeleton`` is a standing person (x depth, y
lateral with the left joints at +y, z up) with a smooth sway along y; no joint is ever exactly (0, 0, 0).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

KINECT_V2 = (
    "SpineBase", "SpineMid", "Neck", "Head", "ShoulderLeft", "ElbowLeft", "WristLeft", "HandLeft",
    "ShoulderRight", "ElbowRight", "WristRight", "HandRight", "HipLeft", "KneeLeft", "AnkleLeft", "FootLeft",
    "HipRight", "KneeRight", "AnkleRight", "FootRight", "SpineShoulder", "HandTipLeft", "ThumbLeft", "HandTipRight",
    "ThumbRight",
)  # fmt: skip
K = {name: i for i, name in enumerate(KINECT_V2)}

STAND = {
    "SpineBase": (0, 0), "SpineMid": (0, 300), "Neck": (0, 600), "Head": (0, 800), "SpineShoulder": (0, 560),
    "ShoulderLeft": (180, 550), "ElbowLeft": (250, 300), "WristLeft": (280, 50), "HandLeft": (290, -20),
    "HandTipLeft": (295, -60), "ThumbLeft": (285, -30),
    "ShoulderRight": (-180, 550), "ElbowRight": (-250, 300), "WristRight": (-280, 50), "HandRight": (-290, -20),
    "HandTipRight": (-295, -60), "ThumbRight": (-285, -30),
    "HipLeft": (100, 0), "KneeLeft": (100, -450), "AnkleLeft": (100, -850), "FootLeft": (100, -900),
    "HipRight": (-100, 0), "KneeRight": (-100, -450), "AnkleRight": (-100, -850), "FootRight": (-100, -900),
}  # fmt: skip

LICENSE = "Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)\n"


def skeleton(i: int = 0, shift: float = 0.0) -> np.ndarray:
    """``(25, 3)`` mm: the standing pose with a sway of the whole body along y; ``shift`` moves it along y."""
    out = np.zeros((25, 3))
    for name, (y, z) in STAND.items():
        out[K[name]] = (-3300.0, y + 30.0 * np.sin(2 * np.pi * i * 0.033 / 4.0) + shift, z)
    return out


def line(ts: int, joints: np.ndarray) -> str:
    return " ".join([str(ts), *(repr(float(v)) for v in joints.reshape(-1))])


def text_of(rows: list[str], eol: str = "\n") -> str:
    return eol.join(rows) + eol


def clean_text(n: int = 60, t0: int = 1_000_000) -> str:
    """``n`` rows at 33 ms steps, nothing wrong."""
    return text_of([line(t0 + 33 * i, skeleton(i)) for i in range(n)])


def synthetic_file() -> str:
    """400 rows: a dropped frame after row 100, a pause of 400 ms after row 200, two bodies for the timestamps of rows
    300 to 305 (the second body 600 mm away), the left wrist at (0, 0, 0) in rows 50 to 52; 406 lines in all."""
    rows = []
    t = 1_000_000
    for i in range(400):
        xyz = skeleton(i)
        if 50 <= i <= 52:
            xyz[K["WristLeft"]] = (0.0, 0.0, 0.0)
        rows.append(line(t, xyz))
        if 300 <= i <= 305:
            rows.append(line(t, skeleton(i, shift=600.0)))
        t += 66 if i == 100 else 400 if i == 200 else 33
    return text_of(rows)


def dataset_name(i: int) -> str:
    """The i-th of 111 distinct names ``PxxTxxCxx``."""
    return f"P{i // 100 + 1:02d}T{i // 10 % 10 + 1:02d}C{i % 10 + 1:02d}"


def make_dataset(
    root: Path, count: int = 111, license_text: str | None = LICENSE, content: str | None = None, rows: int = 20
) -> Path:
    """``root/extracted/Kinect`` with ``count`` small valid files (or ``content``) and a ``License.txt``."""
    folder = root / "extracted" / "Kinect"
    folder.mkdir(parents=True)
    body = clean_text(rows) if content is None else content
    for i in range(count):
        (folder / f"{dataset_name(i)}.txt").write_text(body, encoding="ascii")
    if license_text is not None:
        (folder / "License.txt").write_text(license_text, encoding="ascii")
    return folder
