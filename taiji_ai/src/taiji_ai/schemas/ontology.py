"""Ontology v0: the labels every segment, reference and comparison rule uses (P1.04).

The ontology file (``taiji_ai/config/ontology_v0.yaml``) fixes which actions of the form exist, which sides, view
categories and quality flags are allowed, and how often a movement is repeated. The ``segment`` table of migration
0001 checks only ``view_category``; ``segment.action`` and ``segment.side`` are free text there, so
:meth:`Ontology.check_segment` is their only guard (P8.06 calls it before writing a segment).

Conventions
-----------
* An **action** is one *numbered movement* of the 24-form (24 actions). ``sides`` lists the sides that occur inside
  the movement (``["left", "right"]`` for a movement that alternates, ``["left"]`` for one numbered per side,
  ``["none"]`` for a movement without a side). ``repetitions`` is how often the movement is performed inside its
  number; a segment's ``occurrence`` is the repetition index, ``1..repetitions`` (``None`` = the whole movement).
  The optional ``side_sequence`` gives the side of repetition 1, 2, ... (same length as ``repetitions``, every side of
  ``sides`` occurring); absent means "not specified" and no pairing is checked (nothing is guessed).
* ``technique`` groups numbers that are the same technique (e.g. the two "single whip" numbers); whether a reference
  may come from the other number is decided later (P6.05), not here.
* ``side=None`` means ``"none"`` (the database column is nullable).
* The file is read from the project folder (``config.PROJECT_ROOT``), not from the installed package: the wheel packs
  only ``src/taiji_ai``.
* Content status: ``draft_unconfirmed`` until the coach signs (AGENTS.md §5.12); ``confirmed`` needs ``confirmed_by``
  (a role, never a name) and ``confirmed_at`` (ISO date).

Idea source (AGENTS.md §9.2.5): the shape of an action list with sides comes from the knowledge-base schema of
OpenWushu (github.com/cloudsbird/OpenWushu, commit 53d4e20616c209479246a3ec91d711498becfaf9; content CC BY-SA 4.0,
which publishes a 42-movement routine, not the 24-form). Only the idea is used; no wording or data is copied.
"""

from __future__ import annotations

import collections.abc
import logging
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, field_validator, model_validator

from taiji_ai.config import PROJECT_ROOT

log = logging.getLogger(__name__)

SCHEMA_VERSION = "ontology/1"
DEFAULT_ONTOLOGY_PATH = PROJECT_ROOT / "config" / "ontology_v0.yaml"

_NAME = r"^[a-z][a-z0-9_]*$"
_Name = Annotated[str, StringConstraints(pattern=_NAME)]
_Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
_PositiveInt = Annotated[int, Field(strict=True, ge=1)]


class OntologyError(ValueError):
    """The ontology file is invalid, or a label is not in the ontology. The message lists the valid values."""


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _unique(values: tuple[str, ...], what: str) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError(f"{what} contains a duplicate value: {list(values)}")
    return values


class FormInfo(_Frozen):
    """The form itself and the review status of the content."""

    id: _Name
    name_en: _Text
    expected_actions: _PositiveInt
    status: Literal["draft_unconfirmed", "confirmed"]
    confirmed_by: _Text | None = None  # a role (e.g. "H1"), never a person's name
    confirmed_at: date | None = None  # ISO date

    @model_validator(mode="after")
    def _status_matches_confirmation(self) -> Self:
        has_by, has_at = self.confirmed_by is not None, self.confirmed_at is not None
        if self.status == "confirmed" and not (has_by and has_at):
            raise ValueError("status is confirmed, so both confirmed_by and confirmed_at are required")
        if self.status == "draft_unconfirmed" and (has_by or has_at):
            raise ValueError("status is draft_unconfirmed (draft), so it must not carry confirmed_by or confirmed_at")
        return self


class Action(_Frozen):
    """One numbered movement of the form."""

    id: str = Field(pattern=r"^A\d{2}$")
    slug: _Name
    technique: _Name
    name_en: _Text
    name_zh: _Text
    name_vi: _Text
    sides: tuple[_Name, ...] = Field(min_length=1)
    repetitions: _PositiveInt
    side_sequence: tuple[_Name, ...] | None = None  # side of repetition 1, 2, ...; None = not specified

    @field_validator("sides")
    @classmethod
    def _sides_unique(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        return _unique(v, "sides")

    @model_validator(mode="after")
    def _side_sequence_matches_sides_and_repetitions(self) -> Self:
        seq = self.side_sequence
        if seq is None:
            return self
        if len(seq) != self.repetitions:
            raise ValueError(f"side_sequence has {len(seq)} entries but repetitions is {self.repetitions}")
        outside = [s for s in seq if s not in self.sides]
        if outside:
            raise ValueError(f"side_sequence uses {outside}, which are not in sides {list(self.sides)}")
        unused = [s for s in self.sides if s not in seq]
        if unused:
            raise ValueError(f"side_sequence never uses {unused}, but every side listed in sides must occur in it")
        return self


class Ontology(_Frozen):
    """The validated ontology: vocabularies plus the 24 actions."""

    schema_version: str
    ontology_version: _Text
    form: FormInfo
    sides: tuple[_Name, ...] = Field(min_length=1)
    view_categories: tuple[_Name, ...] = Field(min_length=1)
    flags: tuple[_Name, ...] = Field(min_length=1)
    actions: tuple[Action, ...] = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _schema_version_is_supported(cls, v: str) -> str:
        if v != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION!r}, got {v!r}")
        return v

    @field_validator("sides", "view_categories", "flags")
    @classmethod
    def _vocabulary_unique(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        return _unique(v, "vocabulary")

    @model_validator(mode="after")
    def _cross_checks(self) -> Self:
        problems: list[str] = []
        for what, values in (("id", [a.id for a in self.actions]), ("slug", [a.slug for a in self.actions])):
            seen: set[str] = set()
            for value in values:
                if value in seen:
                    problems.append(f"duplicate action {what} {value!r}")
                seen.add(value)
        for a in self.actions:
            bad = [s for s in a.sides if s not in self.sides]
            if bad:
                problems.append(f"action {a.id}: sides {bad} are not in the declared sides {list(self.sides)}")
        if self.form.expected_actions != len(self.actions):
            problems.append(
                f"form.expected_actions is {self.form.expected_actions} but the file lists {len(self.actions)} actions"
            )
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def check_segment(
        self,
        action: str,
        side: str | None,
        view_category: str,
        flags: Mapping[str, object] | None = None,
        occurrence: int | None = None,
    ) -> Action:
        """Check the labels of one segment and return its :class:`Action`.

        ``side=None`` means ``"none"``. ``occurrence=None`` means the whole movement; an integer must be in
        ``1..action.repetitions``. ``flags`` keys must be declared flags with boolean values.

        Side pairing: if the action has a ``side_sequence`` and ``occurrence`` is an integer, ``side`` must be the
        side of that repetition (e.g. A02: left, right, left). Without a sequence (not specified in the file; A06 and
        A10 in v0) or with ``occurrence=None`` (a whole movement) any listed side is accepted: the file does not say
        which side a whole alternating movement carries (Q9 in ``Docs/tasks/X.18.md``; Q8 in ``Docs/tasks/P1.04.md``).

        Raises:
            OntologyError: a label is not allowed; the message names the valid values.
        """
        found = next((a for a in self.actions if a.id == action), None)
        if found is None:
            raise OntologyError(f"unknown action {action!r}; valid ids: {', '.join(a.id for a in self.actions)}")
        side_label = "none" if side is None else side
        if side_label not in found.sides:
            raise OntologyError(
                f"side {side_label!r} is not allowed for action {found.id}; allowed sides: {', '.join(found.sides)}"
            )
        if view_category not in self.view_categories:
            raise OntologyError(
                f"unknown view_category {view_category!r}; valid values: {', '.join(self.view_categories)}"
            )
        for key, value in (flags or {}).items():
            if key not in self.flags:
                raise OntologyError(f"unknown flag {key!r}; valid flags: {', '.join(self.flags)}")
            if not isinstance(value, bool):
                raise OntologyError(f"flag {key!r} must be a boolean, got {type(value).__name__}")
        if occurrence is not None and (
            not isinstance(occurrence, int) or isinstance(occurrence, bool) or not 1 <= occurrence <= found.repetitions
        ):
            raise OntologyError(
                f"occurrence must be an integer between 1 and {found.repetitions} "
                f"(the repetitions of {found.id}) or None, got {occurrence!r}"
            )
        if found.side_sequence is not None and occurrence is not None:
            expected = found.side_sequence[occurrence - 1]
            if side_label != expected:
                raise OntologyError(
                    f"side {side_label!r} does not match occurrence {occurrence} of {found.id}; "
                    f"the side of that repetition is {expected!r}"
                )
        return found


class _UniqueKeyLoader(yaml.SafeLoader):
    """``SafeLoader`` that rejects a repeated mapping key (``safe_load`` silently keeps the last value)."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.Node, deep: bool = False) -> dict[object, object]:
    if isinstance(node, yaml.MappingNode):
        loader.flatten_mapping(node)
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if not isinstance(key, collections.abc.Hashable):
                continue  # the base class below raises its own error for an unhashable key
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping", node.start_mark, f"found duplicate key {key!r}", key_node.start_mark
                )
            seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def _format_validation_error(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors(include_url=False, include_context=False, include_input=False):
        where = ".".join(str(part) for part in err["loc"]) or "<document>"
        lines.append(f"{where}: {err['msg']}")
    return "ontology is invalid:\n  " + "\n  ".join(lines)


def parse_ontology(data: object) -> Ontology:
    """Validate an already parsed document.

    Raises:
        OntologyError: the document is not a mapping or violates the schema.
    """
    if not isinstance(data, Mapping):
        raise OntologyError(f"the top level of the ontology must be a mapping, got {type(data).__name__}")
    try:
        onto = Ontology.model_validate(data)
    except ValidationError as exc:
        raise OntologyError(_format_validation_error(exc)) from exc
    log.debug("ontology %s loaded: %d actions, status %s", onto.ontology_version, len(onto.actions), onto.form.status)
    return onto


def load_ontology(path: Path | str = DEFAULT_ONTOLOGY_PATH) -> Ontology:
    """Read and validate an ontology YAML file (``safe_load`` only; a duplicated key is an error).

    Raises:
        FileNotFoundError: the file does not exist.
        OntologyError: invalid UTF-8, invalid YAML (including unsafe tags and duplicate keys) or a schema violation.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise OntologyError("the ontology file is not valid UTF-8") from exc
    try:
        data = yaml.load(text, Loader=_UniqueKeyLoader)  # noqa: S506 - a SafeLoader subclass, no object construction
    except yaml.YAMLError as exc:
        raise OntologyError(f"the ontology file is not valid YAML: {exc}") from exc
    return parse_ontology(data)
