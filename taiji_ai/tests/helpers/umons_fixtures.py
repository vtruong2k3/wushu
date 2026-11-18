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


# --- P6.07: segmented files, label files and recordings with a movement (made here, never read from the dataset) -----
def bump(u: float, period: float = 2.0) -> float:
    """A smooth rise and fall between 0 and 1 over ``period`` seconds of movement time ``u``."""
    return 0.5 * (1.0 - float(np.cos(2.0 * np.pi * u / period)))


def motion_skeleton(klass: int, u: float) -> np.ndarray:
    """``(25, 3)`` mm: the standing pose and one movement per class, ``u`` the movement time [s]: class 1 raises the
    left arm, class 2 swings the right arm sideways, class 3 opens both knees; any other class raises both arms."""
    out = skeleton(0)
    b = bump(u)
    if klass == 1:
        for name in ("WristLeft", "HandLeft", "HandTipLeft", "ThumbLeft"):
            out[K[name], 2] += 450.0 * b
        out[K["ElbowLeft"], 2] += 250.0 * b
    elif klass == 2:
        for name in ("ElbowRight", "WristRight", "HandRight", "HandTipRight", "ThumbRight"):
            out[K[name], 1] -= 350.0 * b
    elif klass == 3:
        out[K["KneeLeft"], 1] += 250.0 * b
        out[K["KneeRight"], 1] -= 250.0 * b
        out[K["AnkleLeft"], 1] += 120.0 * b
        out[K["AnkleRight"], 1] -= 120.0 * b
    else:
        for name in ("WristLeft", "HandLeft", "WristRight", "HandRight"):
            out[K[name], 2] += 400.0 * b
    return out


def segment_text(klass: int, rows: int = 70, speed: float = 1.0, t0: int = 2_000_000) -> str:
    """``rows`` Kinect rows at 33 ms steps of one class's movement, performed at ``speed`` (movement time is
    ``speed * t``)."""
    return text_of([line(t0 + 33 * i, motion_skeleton(klass, speed * i * 0.033)) for i in range(rows)])


def routine_skeleton(u: float) -> np.ndarray:
    """``(25, 3)`` mm: a movement whose joints sweep at their own rates with a chirp, so that no two instants look
    alike; ``u`` is the routine time [s], the same for every performer (a performer's own clock is ``u / speed``)."""
    out = skeleton(0)
    phase = 2.0 * np.pi * (0.20 * u + 0.035 * u * u)
    out[K["WristLeft"], 2] += 400.0 * np.sin(phase)
    out[K["HandLeft"], 2] += 400.0 * np.sin(phase)
    out[K["WristRight"], 1] -= 300.0 * np.sin(1.7 * phase + 0.5)
    out[K["HandRight"], 1] -= 300.0 * np.sin(1.7 * phase + 0.5)
    out[K["ElbowLeft"], 1] += 150.0 * np.sin(0.6 * phase + 1.0)
    out[K["KneeLeft"], 1] += 200.0 * np.sin(0.8 * phase + 2.0)
    out[K["KneeRight"], 1] -= 200.0 * np.sin(1.3 * phase + 0.2)
    return out


def routine_text(span_s: float = 6.6, speed: float = 1.0, t0: int = 3_000_000) -> str:
    """The routine up to routine time ``span_s``, performed at ``speed`` (so it lasts ``span_s / speed`` seconds on the
    clock of the file), rows at 33 ms steps."""
    rows = int(round(span_s / speed / 0.033))
    return text_of([line(t0 + 33 * i, routine_skeleton(speed * i * 0.033)) for i in range(rows)])


def segment_name(
    performer: int, klass: int, side: int = 1, repetition: int = 1, trial: int = 1, capture: int = 1
) -> str:
    return f"P{performer:02d}T{trial:02d}C{capture:02d}G{klass:02d}D{side:02d}S{repetition:02d}"


def make_segments(
    root: Path,
    classes: tuple[int, ...] = (1, 2, 3),
    performers: tuple[int, ...] = (1, 2, 3, 4),
    sides: tuple[int, ...] = (1, 2),
    repetitions: tuple[int, ...] = (1, 2),
    rows: int = 70,
    license_text: str | None = LICENSE,
) -> Path:
    """``root/extracted/Segmented_Kinect`` with one made-up file per class, performer, side and repetition: the class's
    movement, a little faster for a higher performer number (a performer is a speed)."""
    folder = root / "extracted" / "Segmented_Kinect"
    folder.mkdir(parents=True, exist_ok=True)
    for g in classes:
        for p in performers:
            for d in sides:
                for s in repetitions:
                    text = segment_text(g, rows=rows, speed=1.0 + 0.04 * p)
                    (folder / f"{segment_name(p, g, d, s)}.txt").write_text(text, encoding="ascii")
    if license_text is not None:
        (folder / "License.txt").write_text(license_text, encoding="ascii")
    return folder


def make_labels(root: Path, files: dict[str, str], license_text: str | None = LICENSE) -> Path:
    """``root/extracted/Labels`` with the given ``PxxTxxCxx`` -> label text files (written as bytes: the text keeps its
    line endings)."""
    folder = root / "extracted" / "Labels"
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (folder / f"{name}.lab").write_bytes(text.encode("ascii"))
    if license_text is not None:
        (folder / "License.txt").write_text(license_text, encoding="ascii")
    return folder


ROUTINE_LABELS = ((0.0, "_"), (1.0, "ex1l"), (2.5, "_"), (3.5, "tech2r"), (5.0, "_"))  # routine time [s], label


def routine_label_text(speed: float = 1.0, eol: str = "\n", shift: float = 0.0) -> str:
    """The labels of ``ROUTINE_LABELS`` for a performer at ``speed`` (an onset at routine time ``u`` is at ``u / speed``
    on the performer's clock), every onset moved by ``shift`` seconds."""
    return "".join(f"{u / speed + shift:.3f} {label}{eol}" for u, label in ROUTINE_LABELS)


def make_boundary_dataset(root: Path, labels_of_two: tuple[str, str] | None = None) -> Path:
    """The 111 made-up Kinect files (``make_dataset``) with two of them replaced by the routine at two speeds
    (``P01T01C03`` at 1.0 and ``P02T01C03`` at 1.25), and the ``Labels`` folder: both recordings labelled with the same
    sequence (the second with some CR line endings), ``P01T01C04`` and ``P02T01C04`` labelled differently, and
    ``P03T01C03`` labelled with no Kinect file."""
    kinect = make_dataset(root, rows=20)
    (kinect / "P01T01C03.txt").write_text(routine_text(speed=1.0), encoding="ascii")
    (kinect / "P02T01C03.txt").write_text(routine_text(speed=1.25), encoding="ascii")
    first, second = labels_of_two or (routine_label_text(1.0), routine_label_text(1.25, eol="\r\n"))
    make_labels(
        root,
        {
            "P01T01C03": first,
            "P02T01C03": second,
            "P01T01C04": "0.0 _\n1.0 ex2l\n2.0 _\n",
            "P02T01C04": "0.0 _\n1.0 ex3l\n2.0 _\n",
            "P03T01C03": routine_label_text(1.0),
        },
    )
    return root
