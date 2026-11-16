"""T-DATA-05i: the command line ``taiji participant add | set | show`` (P2.08).

Results go to standard output, errors to standard error; exit code 0 ok, 1 refused, 2 usage (argparse). Only IDs are
echoed or logged: no path, no free text.
"""

from __future__ import annotations

import tomllib
from datetime import date, timedelta

import pytest

from taiji_ai.cli import main
from taiji_ai.config import PROJECT_ROOT, Settings
from taiji_ai.store.db import connect
from taiji_ai.store.participants import get_participant

pytestmark = pytest.mark.usefixtures("clean_logging")  # main() installs the console log handler


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data")


def run(argv, settings, capsys):
    code = main(argv, settings=settings)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


ADD = ["participant", "add", "--id", "P03", "--consent-ref", "CONSENT-2026-011", "--analysis", "yes", "--train", "no"]
ADD_TAIL = ["--share", "yes", "--actor", "cli:O"]


def _stored(settings, participant_id="P03"):
    conn = connect(settings.db_path, settings.migrations_dir)
    try:
        return get_participant(conn, participant_id)
    finally:
        conn.close()


def _future() -> str:
    return (date.today() + timedelta(days=365)).isoformat()


def test_t_data_05i_add_show_set_round_trip(settings, capsys):
    code, out, _ = run([*ADD, *ADD_TAIL, "--retention", _future()], settings, capsys)
    assert code == 0 and "P03" in out
    p = _stored(settings)
    assert p is not None and (p.consent_analysis, p.consent_train, p.consent_share) == (True, False, True)

    code, out, _ = run(["participant", "show", "--id", "P03"], settings, capsys)
    assert code == 0
    lines = dict(line.split(": ", 1) for line in out.strip().splitlines())
    assert lines["participant_id"] == "P03" and lines["consent_ref"] == "CONSENT-2026-011"
    assert (lines["consent_analysis"], lines["consent_train"], lines["consent_share"]) == ("yes", "no", "yes")
    assert lines["retention_until"] == _future()

    code, out, _ = run(["participant", "set", "--id", "P03", "--train", "yes", "--actor", "cli:O"], settings, capsys)
    assert code == 0
    p = _stored(settings)
    assert p is not None and p.consent_train is True and p.consent_share is True


def test_t_data_05i_show_prints_a_dash_for_a_missing_retention(settings, capsys):
    assert run([*ADD, *ADD_TAIL], settings, capsys)[0] == 0
    code, out, _ = run(["participant", "show", "--id", "P03"], settings, capsys)
    assert code == 0 and "retention_until: -" in out


def test_t_data_05i_set_can_clear_the_retention(settings, capsys):
    assert run([*ADD, *ADD_TAIL, "--retention", _future()], settings, capsys)[0] == 0
    code, _, _ = run(["participant", "set", "--id", "P03", "--clear-retention", "--actor", "cli:O"], settings, capsys)
    assert code == 0
    p = _stored(settings)
    assert p is not None and p.retention_until is None


def test_t_data_05i_analysis_no_is_refused_with_exit_1_and_writes_nothing(settings, capsys):
    argv = [*ADD, *ADD_TAIL]
    argv[argv.index("--analysis") + 1] = "no"
    code, out, err = run(argv, settings, capsys)
    assert code == 1 and out == "" and "analysis consent is required" in err
    assert _stored(settings) is None


def test_t_data_05i_a_duplicate_and_unknown_ids_are_refused(settings, capsys):
    assert run([*ADD, *ADD_TAIL], settings, capsys)[0] == 0
    code, _, err = run([*ADD, *ADD_TAIL], settings, capsys)
    assert code == 1 and "already registered" in err
    code, _, err = run(["participant", "show", "--id", "P09"], settings, capsys)
    assert code == 1 and "not registered" in err
    code, _, err = run(["participant", "set", "--id", "P09", "--train", "yes", "--actor", "cli:O"], settings, capsys)
    assert code == 1 and "not registered" in err


def test_t_data_05i_nothing_to_set_and_a_past_retention_are_refused(settings, capsys):
    assert run([*ADD, *ADD_TAIL], settings, capsys)[0] == 0
    code, _, err = run(["participant", "set", "--id", "P03", "--actor", "cli:O"], settings, capsys)
    assert code == 1 and "nothing to change" in err
    past = (date.today() - timedelta(days=1)).isoformat()
    code, _, err = run(["participant", "set", "--id", "P03", "--retention", past, "--actor", "cli:O"], settings, capsys)
    assert code == 1 and "in the past" in err


def test_t_data_05i_a_name_is_not_an_actor(settings, capsys):
    argv = [*ADD, "--share", "yes", "--actor", "cli:Quang"]
    code, _, err = run(argv, settings, capsys)
    assert code == 1 and "actor" in err
    assert _stored(settings) is None


@pytest.mark.parametrize(
    "argv",
    [
        [
            "participant",
            "add",
            "--id",
            "P03",
            "--consent-ref",
            "CONSENT-2026-011",
            "--train",
            "no",
            *ADD_TAIL,
        ],  # no --analysis
        [
            "participant",
            "add",
            "--id",
            "P03",
            "--consent-ref",
            "CONSENT-2026-011",
            "--analysis",
            "yes",
            *ADD_TAIL,
        ],  # no --train
        [*ADD, "--actor", "cli:O"],  # no --share
        [*ADD, "--share", "yes"],  # no --actor
        [*ADD, "--share", "maybe", "--actor", "cli:O"],  # not yes or no
        ["participant", "set", "--id", "P03", "--train", "yes"],  # no --actor
        ["participant", "set", "--id", "P03", "--retention", "2030-01-01", "--clear-retention", "--actor", "cli:O"],
        ["participant"],  # no sub-command
        [],  # no command
    ],
    ids=[
        "no-analysis",
        "no-train",
        "no-share",
        "no-actor",
        "bad-answer",
        "set-no-actor",
        "retention-and-clear",
        "no-subcommand",
        "no-command",
    ],
)
def test_t_data_05i_a_usage_error_exits_with_2_and_writes_nothing(settings, capsys, argv):
    with pytest.raises(SystemExit) as exc:
        main(argv, settings=settings)
    assert exc.value.code == 2
    capsys.readouterr()
    assert not settings.db_path.exists() or _stored(settings) is None


@pytest.mark.parametrize(
    "argv",
    [
        ["participant", "show", "--id", "Nguyen-Van-A"],
        ["participant", "set", "--id", "Nguyen-Van-A", "--train", "yes", "--actor", "cli:O"],
        ["participant", "add", "--id", "Nguyen-Van-A", "--consent-ref", "CONSENT-2026-011", "--analysis", "yes",
         "--train", "no", "--share", "no", "--actor", "cli:O"],
        ["participant", "add", "--id", "P03", "--consent-ref", "Nguyen-Van-A", "--analysis", "yes",
         "--train", "no", "--share", "no", "--actor", "cli:O"],
        ["participant", "add", "--id", "P03", "--consent-ref", "CONSENT-2026-011", "--analysis", "yes",
         "--train", "no", "--share", "no", "--retention", "Nguyen-Van-A", "--actor", "cli:O"],
    ],
    ids=["show", "set", "add-id", "add-consent-ref", "add-retention"],
)  # fmt: skip
def test_t_data_05i_a_name_given_as_a_value_is_refused_and_never_echoed(settings, capsys, argv):
    """BUG-0050: only a checked pseudonym may appear in a message; invalid text is described, never repeated."""
    code, out, err = run(argv, settings, capsys)
    assert code == 1
    assert "Nguyen" not in out + err and "Van" not in out + err


def test_t_data_05i_setting_the_current_values_says_no_change(settings, capsys):
    assert run([*ADD, *ADD_TAIL], settings, capsys)[0] == 0  # train no, share yes
    code, out, _ = run(["participant", "set", "--id", "P03", "--train", "no", "--actor", "cli:O"], settings, capsys)
    assert code == 0 and out.strip() == "no change for P03"


def test_t_data_05i_nothing_echoes_a_path(settings, capsys, tmp_path):
    out_all = ""
    for argv in (
        [*ADD, *ADD_TAIL],
        ["participant", "show", "--id", "P03"],
        ["participant", "show", "--id", "P09"],
        [*ADD, *ADD_TAIL],
    ):
        _, out, err = run(argv, settings, capsys)
        out_all += out + err
    assert str(tmp_path) not in out_all and "app.sqlite3" not in out_all


def test_t_data_05i_the_taiji_command_is_declared_in_pyproject():
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["scripts"]["taiji"] == "taiji_ai.cli:main"
