"""The review file of the failure review (P3.08): vocabulary, validation, the score of each labelled joint.

``review.csv`` has one row per candidate frame. The columns after the frame's data are two opinions of the same shape:
``a_*`` (filled first by the agent from the sheets) and ``h_*`` (the person who confirms or corrects: a field left
empty means "I agree with the agent's value", except that an ``ok`` verdict clears the agent's failure fields;
``h_confirmed`` is ``yes`` when the person has looked at the row). The
**final** label of a row is the person's value where there is one, else the agent's. Both are validated against one
vocabulary, fixed before the review: the verdict (``ok`` or ``failure``), the failure type, the joints (names of
``halpe26/1`` or the groups ``head``, ``trunk``, ``arms``, ``legs``, ``feet``, ``all``), the severity (``S1`` a limb
on the wrong side or on another body part, or no person; ``S2`` a joint visibly off; ``S3`` minor, listed and not
counted), the view and the situation (the categories of the ontology), and whether the failure is due to the detector
cadence.

The score of each labelled joint comes from the data (``score_warns``), never from the reviewer: a failure is **not
warned** by the score when at least one wrong joint has a score at or above ``tau_kp``, so that a mask at ``tau_kp``
would keep it.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

import numpy as np

from taiji_ai.audit import AuditError
from taiji_ai.bench.compare import JOINT_GROUPS
from taiji_ai.pose.skeleton import JOINTS

VERDICTS: Final = ("ok", "failure")
FAILURE_TYPES: Final = (
    "lr_swap", "joint_off", "hidden_guess", "foot_error", "flicker", "wrong_person", "missed_person", "other",
)  # fmt: skip
NEEDS_JOINTS: Final = frozenset({"lr_swap", "joint_off", "hidden_guess", "foot_error", "flicker"})
SEVERITIES: Final = ("S1", "S2", "S3")
VIEWS: Final = ("front", "side", "oblique", "back", "unknown")
SITUATIONS: Final = ("none", "occlusion", "orientation_change", "one_leg")
CADENCE: Final = ("both", "n5_only", "n1_only", "unknown")
JOINT_TOKENS: Final = frozenset(JOINTS) | frozenset(JOINT_GROUPS) | {"all"}
LABEL_FIELDS: Final = ("verdict", "type", "joints", "severity", "view", "situation", "cadence", "note")
DATA_COLUMNS: Final = ("id", "video", "frame_index", "t_sec", "tags")
COLUMNS: Final = (
    *DATA_COLUMNS,
    *(f"a_{f}" for f in LABEL_FIELDS),
    *(f"h_{f}" for f in LABEL_FIELDS),
    "h_confirmed",
)
_VOCAB = {
    "verdict": VERDICTS, "type": FAILURE_TYPES, "severity": SEVERITIES, "view": VIEWS, "situation": SITUATIONS,
    "cadence": CADENCE,
}  # fmt: skip


@dataclass(frozen=True)
class Label:
    """One opinion; an empty string is "not given" (``joints`` is a tuple of tokens, empty when none)."""

    verdict: str = ""
    type: str = ""
    joints: tuple[str, ...] = ()
    severity: str = ""
    view: str = ""
    situation: str = ""
    cadence: str = ""
    note: str = ""


@dataclass(frozen=True)
class ReviewRow:
    cid: str
    video: str
    frame_index: int
    t_sec: float
    tags: tuple[str, ...]
    a: Label
    h: Label
    h_confirmed: bool


def write_template(path: Path | str, rows: Iterable[tuple[str, str, int, float, Sequence[str]]]) -> None:
    """Write an empty review file: the data columns of each candidate, the opinions empty."""
    with Path(path).open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for cid, video, frame_index, t_sec, tags in rows:
            writer.writerow(
                [cid, video, frame_index, f"{t_sec:.3f}", "|".join(tags)] + [""] * (len(COLUMNS) - len(DATA_COLUMNS))
            )


def _label(raw: dict[str, str], prefix: str) -> Label:
    joints = tuple(j.strip() for j in raw[f"{prefix}_joints"].split("|") if j.strip())
    return Label(
        verdict=raw[f"{prefix}_verdict"].strip(),
        type=raw[f"{prefix}_type"].strip(),
        joints=joints,
        severity=raw[f"{prefix}_severity"].strip(),
        view=raw[f"{prefix}_view"].strip(),
        situation=raw[f"{prefix}_situation"].strip(),
        cadence=raw[f"{prefix}_cadence"].strip(),
        note=raw[f"{prefix}_note"].strip(),
    )


def check_partial(label: Label, where: str) -> None:
    """Every field that is given is in the vocabulary (an empty field is "not given")."""
    for name, vocab in _VOCAB.items():
        value = getattr(label, name)
        if value and value not in vocab:
            raise AuditError(f"{where}: {name} {value!r} is not one of {list(vocab)}")
    for joint in label.joints:
        if joint not in JOINT_TOKENS:
            raise AuditError(
                f"{where}: joint {joint!r} is not a joint name or a group (head, trunk, arms, legs, feet, all)"
            )


def check_complete(label: Label, where: str) -> None:
    """A final label is whole: ``ok`` has no type, joints or severity; ``failure`` has type and severity, and joints for
    the types that name joints; every label has a view and a situation."""
    check_partial(label, where)
    if not label.verdict:
        raise AuditError(f"{where}: verdict is missing")
    if not label.view or not label.situation:
        raise AuditError(f"{where}: view and situation are required")
    if label.verdict == "ok":
        if label.type or label.joints or label.severity:
            raise AuditError(f"{where}: an 'ok' row has no type, joints or severity")
        return
    if not label.type or not label.severity:
        raise AuditError(f"{where}: a failure needs a type and a severity")
    if label.type in NEEDS_JOINTS and not label.joints:
        raise AuditError(f"{where}: a failure of type {label.type!r} names the wrong joints")


def final_label(row: ReviewRow) -> Label:
    """The person's value where there is one, else the agent's, field by field.

    One exception, because an empty field cannot say "none": when the person's verdict is ``ok`` the agent's failure
    fields (type, joints, severity, cadence) are cleared, so that a failure the person finds to be fine becomes a whole
    ``ok`` label (a type or a severity that the person gives with ``ok`` is still refused by ``check_complete``).
    """
    merged = {}
    for name in LABEL_FIELDS:
        h, a = getattr(row.h, name), getattr(row.a, name)
        merged[name] = h if h else a
    if row.h.verdict == "ok":
        for name in ("type", "joints", "severity", "cadence"):
            merged[name] = getattr(row.h, name)
    return replace(row.a, **merged)


def read_review(
    path: Path | str, expected_ids: Iterable[str] | None = None, *, require_agent: bool = True
) -> list[ReviewRow]:
    """Read and validate ``review.csv``.

    Raises:
        AuditError: wrong columns, a repeated, missing or unexpected ID, a value outside the vocabulary, a final label
            that is not whole (when ``require_agent``, every row needs the agent's verdict); the message names the row
            and the field.
    """
    try:
        with Path(path).open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if tuple(reader.fieldnames or ()) != COLUMNS:
                raise AuditError(f"review file: the columns must be exactly {list(COLUMNS)}")
            raw_rows = list(reader)
    except OSError as exc:
        raise AuditError("the review file could not be read") from exc
    rows: list[ReviewRow] = []
    seen: set[str] = set()
    for raw in raw_rows:
        cid = raw["id"].strip()
        if not cid or cid in seen:
            raise AuditError(f"review file: the ID {cid!r} is empty or repeated")
        seen.add(cid)
        try:
            frame_index, t_sec = int(raw["frame_index"]), float(raw["t_sec"])
        except ValueError as exc:
            raise AuditError(f"{cid}: frame_index and t_sec must be numbers") from exc
        confirmed = raw["h_confirmed"].strip().lower()
        if confirmed not in ("", "yes", "no"):
            raise AuditError(f"{cid}: h_confirmed must be empty, 'yes' or 'no'")
        row = ReviewRow(
            cid, raw["video"].strip(), frame_index, t_sec, tuple(x for x in raw["tags"].split("|") if x),
            _label(raw, "a"), _label(raw, "h"), confirmed == "yes",
        )  # fmt: skip
        check_partial(row.a, f"{cid} (agent)")
        check_partial(row.h, f"{cid} (person)")
        if require_agent:
            check_complete(final_label(row), cid)
        rows.append(row)
    if expected_ids is not None:
        expected = set(expected_ids)
        if seen != expected:
            missing, extra = sorted(expected - seen), sorted(seen - expected)
            raise AuditError(f"review file: missing candidates {missing[:5]}, unexpected rows {extra[:5]}")
    return rows


def expand_joints(tokens: Sequence[str]) -> list[int]:
    """The joint indices named by names and groups, sorted, without repeats."""
    indices: set[int] = set()
    for token in tokens:
        if token == "all":
            indices.update(range(len(JOINTS)))
        elif token in JOINT_GROUPS:
            indices.update(JOINTS.index(name) for name in JOINT_GROUPS[token])
        elif token in JOINTS:
            indices.add(JOINTS.index(token))
        else:
            raise AuditError(f"{token!r} is not a joint name or a group")
    return sorted(indices)


def score_warns(joints: Sequence[str], scores: np.ndarray, tau: float) -> bool | None:
    """Would a mask at ``tau`` have removed **every** wrong joint? ``True``: all named joints score under ``tau`` (or
    have no score); ``False``: at least one wrong joint scores at or above it, so the mask keeps it; ``None``: no joint
    named."""
    if not joints:
        return None
    values = np.asarray(scores, dtype=np.float64)[expand_joints(joints)]
    return bool(np.all(~np.isfinite(values) | (values < tau)))


def _given(label: Label, name: str) -> bool:
    return bool(getattr(label, name))


def _same(a: Label, b: Label, name: str) -> bool:
    x, y = getattr(a, name), getattr(b, name)
    return set(x) == set(y) if name == "joints" else bool(x == y)


def agreement(rows: Sequence[ReviewRow]) -> dict[str, tuple[int, int]]:
    """For each label field, ``(rows the person looked at, rows where the person agrees with the agent)``; the person
    agrees where the field is empty or equal to the agent's."""
    looked = [r for r in rows if r.h_confirmed or any(getattr(r.h, f) for f in LABEL_FIELDS)]
    out: dict[str, tuple[int, int]] = {}
    for name in LABEL_FIELDS:
        agree = sum(1 for r in looked if not _given(r.h, name) or _same(r.h, r.a, name))
        out[name] = (len(looked), agree)
    return out
