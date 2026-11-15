"""T-DATA-01: the ontology file and its validator (P1.04).

Covers: the shipped ``config/ontology_v0.yaml`` (24 actions, draft until the coach signs), the schema rules (unique
ids and slugs, declared vocabularies, no unknown keys, confirmation fields), ``check_segment`` (the only guard of
``segment.action`` / ``segment.side``, which the database does not check), agreement of the view list with the
``segment.view_category`` CHECK of migration 0001, and loading (safe YAML, duplicate keys, bad files).
"""

from __future__ import annotations

import copy
import re
from datetime import date
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from taiji_ai.config import PROJECT_ROOT
from taiji_ai.schemas.ontology import (
    DEFAULT_ONTOLOGY_PATH,
    SCHEMA_VERSION,
    OntologyError,
    load_ontology,
    parse_ontology,
)

FLAGS = {"orientation_change", "occlusion", "perspective_shift"}  # TECH_WORKFLOW W3, segment.flags JSON keys


def _valid() -> dict:
    """A minimal valid document with two actions (one alternating sides, three repetitions)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "ontology_version": "v0",
        "form": {"id": "demo", "name_en": "Demo form", "expected_actions": 2, "status": "draft_unconfirmed"},
        "sides": ["left", "right", "none"],
        "view_categories": ["front", "side", "oblique", "back", "unknown"],
        "flags": ["orientation_change", "occlusion", "perspective_shift"],
        "actions": [
            {
                "id": "A01",
                "slug": "opening",
                "technique": "opening",
                "name_en": "Opening",
                "name_zh": "zh-1",
                "name_vi": "vi-1",
                "sides": ["none"],
                "repetitions": 1,
            },
            {
                "id": "A02",
                "slug": "mane",
                "technique": "mane",
                "name_en": "Mane",
                "name_zh": "zh-2",
                "name_vi": "vi-2",
                "sides": ["left", "right"],
                "repetitions": 3,
            },
        ],
    }


# --- T-DATA-01a: the shipped file and a minimal document ----------------------------------------------------------


def test_t_data_01a_shipped_file_loads_and_has_24_actions():
    onto = load_ontology(DEFAULT_ONTOLOGY_PATH)
    assert onto.schema_version == SCHEMA_VERSION
    assert len(onto.actions) == onto.form.expected_actions == 24
    assert [a.id for a in onto.actions] == [f"A{i:02d}" for i in range(1, 25)]
    for a in onto.actions:
        assert a.name_en and a.name_zh and a.name_vi, a.id
    assert onto.form.status in ("draft_unconfirmed", "confirmed")


def test_t_data_01a_minimal_valid_document_parses():
    onto = parse_ontology(_valid())
    assert [a.id for a in onto.actions] == ["A01", "A02"]


# --- T-DATA-01b: duplicates ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["id", "slug"])
def test_t_data_01b_duplicate_action_id_or_slug_is_rejected(key):
    data = _valid()
    data["actions"][1][key] = data["actions"][0][key]
    with pytest.raises(OntologyError, match="duplicate"):
        parse_ontology(data)


# --- T-DATA-01c: vocabularies, unknown keys, version, counts -------------------------------------------------------


def _side_outside_declared(d: dict) -> None:
    d["actions"][1]["sides"] = ["up"]


def _unknown_top_key(d: dict) -> None:
    d["surprise"] = 1


def _unknown_form_key(d: dict) -> None:
    d["form"]["surprise"] = 1


def _unknown_action_key(d: dict) -> None:
    d["actions"][0]["surprise"] = 1


def _wrong_version(d: dict) -> None:
    d["schema_version"] = "ontology/2"


def _missing_flags(d: dict) -> None:
    del d["flags"]


def _expected_count_mismatch(d: dict) -> None:
    d["form"]["expected_actions"] = 3


def _duplicate_declared_side(d: dict) -> None:
    d["sides"] = ["left", "right", "none", "left"]  # still a superset of every action's sides: only the repeat is wrong


def _duplicate_action_side(d: dict) -> None:
    d["actions"][1]["sides"] = ["left", "left"]


def _repetitions_is_a_bool(d: dict) -> None:
    d["actions"][0]["repetitions"] = True


def _repetitions_is_a_string(d: dict) -> None:
    d["actions"][0]["repetitions"] = "3"


def _repetitions_is_a_float(d: dict) -> None:
    d["actions"][0]["repetitions"] = 2.0


def _bad_slug(d: dict) -> None:
    d["actions"][0]["slug"] = "Bad Slug"


def _bad_action_id(d: dict) -> None:
    d["actions"][0]["id"] = "X1"


@pytest.mark.parametrize(
    "mutate",
    [
        _side_outside_declared,
        _unknown_top_key,
        _unknown_form_key,
        _unknown_action_key,
        _wrong_version,
        _missing_flags,
        _expected_count_mismatch,
        _duplicate_declared_side,
        _duplicate_action_side,
        _repetitions_is_a_bool,
        _repetitions_is_a_string,
        _repetitions_is_a_float,
        _bad_slug,
        _bad_action_id,
    ],
)
def test_t_data_01c_invalid_document_is_rejected(mutate):
    data = copy.deepcopy(_valid())
    mutate(data)
    with pytest.raises(OntologyError):
        parse_ontology(data)


def test_t_data_01c_errors_name_the_field():
    data = _valid()
    data["actions"][1]["sides"] = ["up"]
    with pytest.raises(OntologyError, match=r"sides"):
        parse_ontology(data)
    data = _valid()
    data["form"]["expected_actions"] = 3
    with pytest.raises(OntologyError, match=r"expected_actions"):
        parse_ontology(data)


# --- T-DATA-01d: check_segment ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def shipped():
    return load_ontology(DEFAULT_ONTOLOGY_PATH)


def _allowed_sides(action, occurrence):
    """Sides accepted for ``occurrence``: the side of that repetition when the action has a ``side_sequence``."""
    if action.side_sequence is not None and occurrence is not None:
        return (action.side_sequence[occurrence - 1],)
    return action.sides


def test_t_data_01d_every_valid_label_combination_is_accepted(shipped):
    n = 0
    for action in shipped.actions:
        for view in shipped.view_categories:
            for flags in [{}] + [{f: True} for f in shipped.flags]:
                for occurrence in [None, *range(1, action.repetitions + 1)]:
                    for side in _allowed_sides(action, occurrence):
                        got = shipped.check_segment(action.id, side, view, flags, occurrence)
                        assert got.id == action.id
                        n += 1
    assert n > 1000


def test_t_data_01d_unknown_action_names_the_valid_ids(shipped):
    with pytest.raises(OntologyError, match="A01") as err:
        shipped.check_segment("A99", "none", "front")
    assert "A24" in str(err.value)


def test_t_data_01d_disallowed_side_names_the_allowed_sides(shipped):
    single = next(a for a in shipped.actions if a.sides == ("none",))
    with pytest.raises(OntologyError, match="none"):
        shipped.check_segment(single.id, "left", "front")


def test_t_data_01d_side_none_means_the_word_none_and_is_checked(shipped):
    no_side = next(a for a in shipped.actions if "none" in a.sides)
    assert shipped.check_segment(no_side.id, None, "front").id == no_side.id
    one_sided = next(a for a in shipped.actions if "none" not in a.sides)
    with pytest.raises(OntologyError):
        shipped.check_segment(one_sided.id, None, "front")


@pytest.mark.parametrize("view", ["top", "Front", "", "unknown "])
def test_t_data_01d_unknown_view_is_rejected(shipped, view):
    with pytest.raises(OntologyError, match="front"):
        shipped.check_segment("A01", "none", view)


def test_t_data_01d_unknown_flag_and_non_boolean_flag_are_rejected(shipped):
    with pytest.raises(OntologyError, match="occlusion"):
        shipped.check_segment("A01", "none", "front", {"shaky": True})
    with pytest.raises(OntologyError, match="boolean"):
        shipped.check_segment("A01", "none", "front", {"occlusion": 1})


def test_t_data_01d_occurrence_must_be_within_the_repetitions(shipped):
    action = next(a for a in shipped.actions if a.repetitions > 1)
    for bad in (0, -1, action.repetitions + 1):
        with pytest.raises(OntologyError, match=rf"1 and {action.repetitions}"):
            shipped.check_segment(action.id, action.sides[0], "front", None, bad)
    once = next(a for a in shipped.actions if a.repetitions == 1)
    with pytest.raises(OntologyError):
        shipped.check_segment(once.id, once.sides[0], "front", None, 2)


@pytest.mark.parametrize("bad", [True, "1", 1.0])
def test_t_data_01d_occurrence_must_be_a_real_integer(shipped, bad):
    with pytest.raises(OntologyError, match="integer"):
        shipped.check_segment("A02", "left", "front", None, bad)


# --- T-DATA-01e: confirmation -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"confirmed_by": "H1"},
        {"confirmed_at": "2026-12-01"},
    ],
)
def test_t_data_01e_confirmed_needs_both_confirmed_by_and_confirmed_at(extra):
    data = _valid()
    data["form"].update({"status": "confirmed", **extra})
    with pytest.raises(OntologyError, match="confirmed"):
        parse_ontology(data)


def test_t_data_01e_confirmed_with_both_fields_is_accepted():
    data = _valid()
    data["form"].update({"status": "confirmed", "confirmed_by": "H1", "confirmed_at": "2026-12-01"})
    assert parse_ontology(data).form.status == "confirmed"


def test_t_data_01e_an_unquoted_yaml_date_is_accepted_as_confirmed_at(tmp_path):
    """A coach signs by hand: ``confirmed_at: 2026-12-01`` (no quotes) is a YAML date, not a string."""
    data = _valid()
    data["form"].update({"status": "confirmed", "confirmed_by": "H1", "confirmed_at": date(2026, 12, 1)})
    f = _write(tmp_path / "o.yaml", yaml.safe_dump(data))
    assert "confirmed_at: 2026-12-01" in f.read_text(encoding="utf-8")
    assert load_ontology(f).form.confirmed_at == date(2026, 12, 1)


@pytest.mark.parametrize("field", ["confirmed_by", "confirmed_at"])
def test_t_data_01e_a_draft_must_not_carry_confirmation_fields(field):
    data = _valid()
    data["form"][field] = "H1" if field == "confirmed_by" else "2026-12-01"
    with pytest.raises(OntologyError, match="draft"):
        parse_ontology(data)


# --- T-DATA-01f: agreement with the database ----------------------------------------------------------------------


def test_t_data_01f_views_equal_the_database_check_list(shipped):
    sql = (PROJECT_ROOT / "migrations" / "0001_init.sql").read_text(encoding="utf-8")
    m = re.search(r"view_category\s+TEXT NOT NULL CHECK \(view_category IN \(([^)]*)\)\)", sql)
    assert m, "the CHECK of segment.view_category was not found in migration 0001"
    db_views = re.findall(r"'([^']+)'", m.group(1))
    assert db_views
    assert set(shipped.view_categories) == set(db_views)
    assert len(shipped.view_categories) == len(db_views)


def test_t_data_01f_flags_are_the_three_of_the_workflow(shipped):
    assert set(shipped.flags) == FLAGS


# --- T-DATA-01g: technique, repetitions ---------------------------------------------------------------------------


def test_t_data_01g_every_action_has_a_technique_and_some_techniques_are_shared(shipped):
    assert all(a.technique for a in shipped.actions)
    counts: dict[str, int] = {}
    for a in shipped.actions:
        counts[a.technique] = counts.get(a.technique, 0) + 1
    assert any(c >= 2 for c in counts.values())


@pytest.mark.parametrize("bad", [0, -1])
def test_t_data_01g_repetitions_below_one_are_rejected(bad):
    data = _valid()
    data["actions"][0]["repetitions"] = bad
    with pytest.raises(OntologyError, match="repetitions"):
        parse_ontology(data)


@pytest.mark.parametrize("field", ["technique", "name_en", "name_zh", "name_vi"])
def test_t_data_01g_empty_text_fields_are_rejected(field):
    data = _valid()
    data["actions"][0][field] = ""
    with pytest.raises(OntologyError, match=field):
        parse_ontology(data)


def test_t_data_01g_an_action_without_sides_is_rejected():
    data = _valid()
    data["actions"][0]["sides"] = []
    with pytest.raises(OntologyError, match="sides"):
        parse_ontology(data)


def test_t_data_01g_the_model_is_immutable(shipped):
    with pytest.raises(ValidationError, match="frozen"):
        shipped.actions[0].repetitions = 9  # type: ignore[misc]


# --- T-DATA-01h: loading ------------------------------------------------------------------------------------------


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_t_data_01h_a_valid_file_round_trips(tmp_path):
    f = _write(tmp_path / "o.yaml", yaml.safe_dump(_valid(), allow_unicode=True))
    assert [a.id for a in load_ontology(f).actions] == ["A01", "A02"]


def test_t_data_01h_an_unsafe_tag_is_rejected_and_runs_nothing(tmp_path):
    sentinel = tmp_path / "sentinel"
    payload = f'schema_version: !!python/object/apply:os.makedirs ["{sentinel.as_posix()}"]\n'
    with pytest.raises(OntologyError):
        load_ontology(_write(tmp_path / "o.yaml", payload))
    assert not sentinel.exists()


def test_t_data_01h_a_duplicated_key_is_rejected(tmp_path):
    text = yaml.safe_dump(_valid()) + "ontology_version: v1\n"
    with pytest.raises(OntologyError, match="duplicate"):
        load_ontology(_write(tmp_path / "o.yaml", text))


def test_t_data_01h_invalid_yaml_is_reported_as_yaml(tmp_path):
    with pytest.raises(OntologyError, match="YAML"):
        load_ontology(_write(tmp_path / "o.yaml", "a: [unclosed"))


@pytest.mark.parametrize("text", ["- a\n- b\n", "", "just a string\n"])
def test_t_data_01h_a_top_level_that_is_not_a_mapping_is_rejected(tmp_path, text):
    with pytest.raises(OntologyError, match="mapping"):
        load_ontology(_write(tmp_path / "o.yaml", text))


def test_t_data_01h_invalid_utf8_is_rejected(tmp_path):
    f = tmp_path / "o.yaml"
    f.write_bytes(b"schema_version: \xff\xfe\n")
    with pytest.raises(OntologyError, match="UTF-8"):
        load_ontology(f)


def test_t_data_01h_a_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_ontology(tmp_path / "absent.yaml")


# --- T-DATA-01i: side_sequence schema (X.18) ----------------------------------------------------------------------


def _with_sequence(seq: list[str], index: int = 1) -> dict:
    """``_valid()`` with ``side_sequence`` set on the action at ``index`` (default A02: left/right, 3 repetitions)."""
    data = _valid()
    data["actions"][index]["side_sequence"] = seq
    return data


def test_t_data_01i_a_valid_side_sequence_is_accepted():
    onto = parse_ontology(_with_sequence(["left", "right", "left"]))
    assert onto.actions[1].side_sequence == ("left", "right", "left")


def test_t_data_01i_an_absent_sequence_is_accepted_even_for_an_alternating_action():
    """Unknown stays unknown: nothing forces a guess into the file."""
    assert parse_ontology(_valid()).actions[1].side_sequence is None


def test_t_data_01i_a_single_side_action_may_carry_a_matching_sequence():
    assert parse_ontology(_with_sequence(["none"], index=0)).actions[0].side_sequence == ("none",)


@pytest.mark.parametrize(
    "seq",
    [
        ["left", "right"],  # shorter than repetitions
        ["left", "right", "left", "right"],  # longer than repetitions
        [],  # empty
        ["left", "up", "left"],  # a side that the action does not have (and "right" never occurs)
        ["left", "right", "up"],  # a side that the action does not have, every declared side occurs
        ["left", "left", "left"],  # a declared side never occurs
        ["Left", "right", "left"],  # not a valid label
    ],
    ids=["too-short", "too-long", "empty", "outside-sides", "outside-only", "side-never-occurs", "bad-label"],
)
def test_t_data_01i_an_invalid_side_sequence_is_rejected(seq):
    with pytest.raises(OntologyError, match="side_sequence"):
        parse_ontology(_with_sequence(seq))


def test_t_data_01i_a_sequence_outside_the_action_sides_is_rejected_on_a_single_side_action():
    with pytest.raises(OntologyError, match="side_sequence"):
        parse_ontology(_with_sequence(["left"], index=0))


# --- T-DATA-01j: check_segment pairs a side with its repetition ----------------------------------------------------


@pytest.fixture
def sequenced():
    return parse_ontology(_with_sequence(["left", "right", "left"]))


def test_t_data_01j_the_side_of_each_repetition_is_accepted(sequenced):
    for k, side in enumerate(("left", "right", "left"), start=1):
        assert sequenced.check_segment("A02", side, "front", None, k).id == "A02"


def test_t_data_01j_the_other_side_is_rejected_and_the_expected_one_is_named(sequenced):
    with pytest.raises(OntologyError, match=r"occurrence 2 .*'right'"):
        sequenced.check_segment("A02", "left", "front", None, 2)
    with pytest.raises(OntologyError, match=r"occurrence 3 .*'left'"):
        sequenced.check_segment("A02", "right", "front", None, 3)


def test_t_data_01j_a_whole_movement_still_accepts_any_listed_side(sequenced):
    """Q9 is open: with ``occurrence=None`` nothing can be paired, so nothing changes."""
    for side in ("left", "right"):
        assert sequenced.check_segment("A02", side, "front", None, None).id == "A02"


def test_t_data_01j_without_a_sequence_the_pairing_is_not_checked():
    """Unchanged v0 behaviour for an unspecified action (Q8 open for it)."""
    assert parse_ontology(_valid()).check_segment("A02", "right", "front", None, 3).id == "A02"


# --- T-DATA-01k: the shipped file ---------------------------------------------------------------------------------


def test_t_data_01k_every_present_sequence_follows_the_schema(shipped):
    for a in shipped.actions:
        if a.side_sequence is not None:
            assert len(a.side_sequence) == a.repetitions, a.id
            assert set(a.side_sequence) == set(a.sides), a.id


def test_t_data_01k_sequences_exist_only_where_names_or_sources_point_to_one_order(shipped):
    by_id = {a.id: a for a in shipped.actions}
    for action_id in ("A02", "A04", "A18"):
        assert by_id[action_id].side_sequence is not None, action_id
    for action_id in ("A06", "A10"):  # nothing read points to one order: unspecified stays unspecified (Q8, coach)
        assert by_id[action_id].side_sequence is None, action_id


def test_t_data_01k_the_pairing_check_accepts_the_listed_side_and_rejects_the_others(shipped):
    checked = 0
    for a in shipped.actions:
        if a.side_sequence is None:
            continue
        for k, side in enumerate(a.side_sequence, start=1):
            assert shipped.check_segment(a.id, side, "front", None, k).id == a.id
            for other in a.sides:
                if other != side:
                    with pytest.raises(OntologyError, match="does not match"):
                        shipped.check_segment(a.id, other, "front", None, k)
            checked += 1
    assert checked >= 8  # A02 (3) + A04 (3) + A18 (2)
