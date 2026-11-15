"""Shared base of the persisted manifests of Phase 2 (P2.01).

Rules every manifest follows (AGENTS.md sections 5.1, 5.4, 5.8, 5.9, 6):

* Pydantic v2, ``extra="forbid"`` (an unknown key is an error, so nothing slips in by accident) and frozen.
* ``schema_version`` is a ``Literal`` in every manifest class; a change of a field bumps it.
* An unknown value is ``None`` (``null`` in JSON), never 0 or an invented number.
* Floats reject NaN and infinity, so every manifest is valid JSON.
* No field holds a person's name, an original file name or an absolute path.
* Files are written atomically (``store.artifacts``); the manifest of a stage is written last.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from taiji_ai.store.artifacts import atomic_write_json

# Identifier patterns, from the capture protocol (P1.05) and the consent form (P1.06); a change there changes these.
PARTICIPANT_RE = r"^P\d{2,}$"
SESSION_RE = r"^S\d{2,}$"
TAKE_RE = r"^S\d{2,}-P\d{2,}-T\d{2,}$"
CAMERA_RE = r"^cam[A-Z]$"
CONSENT_RE = r"^CONSENT-\d{4}-\d{3,}$"
UUID4_RE = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
SHA256_RE = r"^[0-9a-f]{64}$"

# Numbers. Floats are lax (an integer is accepted as a float), integers are strict (no booleans, no strings).
Seconds = Annotated[float, Field(allow_inf_nan=False)]
NonNeg = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
PosInt = Annotated[int, Field(strict=True, ge=1)]
NonNegInt = Annotated[int, Field(strict=True, ge=0)]


class ManifestError(ValueError):
    """A manifest is invalid or unreadable; the message names the field."""


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Manifest(FrozenModel):
    """A model that is written to disk as a manifest; subclasses declare ``schema_version``."""


class ToolVersions(FrozenModel):
    """Versions of the tools that produced a manifest (provenance, not a threshold)."""

    ffprobe: str = Field(min_length=1)
    pyav: str = Field(min_length=1)
    taiji_ai: str = Field(min_length=1)


def format_validation_error(name: str, exc: ValidationError) -> str:
    lines = []
    for err in exc.errors(include_url=False, include_context=False, include_input=False):
        where = ".".join(str(part) for part in err["loc"]) or "<document>"
        lines.append(f"{where}: {err['msg']}")
    return f"{name} is invalid:\n  " + "\n  ".join(lines)


def parse_manifest[M: FrozenModel](cls: type[M], data: object) -> M:
    """Validate ``data`` as ``cls``.

    Raises:
        ManifestError: a field is missing, of the wrong type or value, or unknown; the message names the field.
    """
    try:
        return cls.model_validate(data)
    except ValidationError as exc:
        raise ManifestError(format_validation_error(cls.__name__, exc)) from exc


def write_manifest(path: str | Path, model: Manifest) -> Path:
    """Write ``model`` as JSON atomically (temporary file, fsync, replace)."""
    return atomic_write_json(path, model.model_dump(mode="json"))


def read_manifest[M: FrozenModel](path: str | Path, cls: type[M]) -> M:
    """Read and validate a manifest file.

    Raises:
        FileNotFoundError: the file does not exist.
        ManifestError: the file is not UTF-8, not JSON, not a JSON object, or does not fit ``cls``.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ManifestError(f"{cls.__name__}: the file is not valid UTF-8") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"{cls.__name__}: the file is not valid JSON ({exc.msg})") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"{cls.__name__}: the top level must be a JSON object, got {type(data).__name__}")
    return parse_manifest(cls, data)
