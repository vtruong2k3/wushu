"""T-IO-19: the command line ``taiji ingest`` (P2.02).

The result goes to standard output, errors to standard error; exit code 0 ok, 1 refused, 2 usage. Only IDs are printed:
never the path or the name of the file.
"""

from __future__ import annotations

import shutil
from contextlib import closing

import pytest

from helpers.media import tamper_pts
from taiji_ai.cli import main
from taiji_ai.io import ingest as ingest_module
from taiji_ai.io.proxy import ProxyError
from taiji_ai.store.db import connect

pytestmark = pytest.mark.usefixtures("clean_logging")  # main() installs the console log handler

NAME = "Tập luyện - Nguyễn Văn A.mp4"
IDS = ["--participant", "P03", "--session", "S01", "--take", "S01-P03-T02", "--camera", "camA"]


@pytest.fixture
def phone_file(tmp_path, cfr_video):
    folder = tmp_path / "phone"
    folder.mkdir()
    dst = folder / NAME
    shutil.copyfile(cfr_video, dst)
    return dst


def run(argv, settings, capsys):
    code = main(argv, settings=settings)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _recordings(settings):
    with closing(connect(settings.db_path, settings.migrations_dir)) as conn:
        return conn.execute("SELECT * FROM recording").fetchall()


def test_t_io_19_ingest_prints_the_recording_id_and_never_the_path(ingest_settings, phone_file, capsys):
    code, out, err = run(["ingest", str(phone_file), *IDS], ingest_settings, capsys)
    [row] = _recordings(ingest_settings)
    assert code == 0 and out.strip() == f"ingested {row['recording_id']} (take S01-P03-T02, camA)"
    text = out + err
    assert NAME not in text and "Nguy" not in text and str(phone_file.parent) not in text and "phone" not in text


def test_t_io_19_the_second_ingest_of_the_same_file_says_so(ingest_settings, phone_file, capsys):
    run(["ingest", str(phone_file), *IDS], ingest_settings, capsys)
    [row] = _recordings(ingest_settings)
    code, out, _ = run(["ingest", str(phone_file), *IDS], ingest_settings, capsys)
    assert code == 0 and out.strip() == f"already ingested {row['recording_id']}"
    assert len(_recordings(ingest_settings)) == 1


def test_t_io_19_capture_info_is_stored(ingest_settings, phone_file, capsys):
    argv = [
        "ingest",
        str(phone_file),
        *IDS,
        "--role",
        "main_axis",
        "--camera-height-m",
        "1.1",
        "--camera-distance-m",
        "4.5",
    ]
    argv += ["--fps-setting", "30"]
    assert run(argv, ingest_settings, capsys)[0] == 0
    from taiji_ai.schemas._base import read_manifest
    from taiji_ai.schemas.recording import RecordingManifest

    [row] = _recordings(ingest_settings)
    manifest = read_manifest(
        ingest_settings.data_dir / "recordings" / row["recording_id"] / "recording.json", RecordingManifest
    )
    assert manifest.capture is not None
    assert (manifest.capture.camera_role, manifest.capture.height_m, manifest.capture.distance_m) == (
        "main_axis",
        1.1,
        4.5,
    )
    assert manifest.capture.fps_setting == 30.0


@pytest.mark.parametrize(
    ("argv_tail", "message"),
    [
        (["--participant", "P04", "--session", "S01", "--take", "S01-P04-T01", "--camera", "camA"], "not registered"),
        (["--participant", "P03", "--session", "S01", "--take", "S01-P09-T02", "--camera", "camA"], "take_id"),
        (
            ["--participant", "Nguyen-Van-A", "--session", "S01", "--take", "S01-P03-T02", "--camera", "camA"],
            "participant_id",
        ),
    ],
    ids=["unregistered", "take-of-someone-else", "a-name-as-participant"],
)
def test_t_io_19_a_refusal_exits_with_1_says_why_and_echoes_no_free_text(
    ingest_settings, phone_file, capsys, argv_tail, message
):
    code, out, err = run(["ingest", str(phone_file), *argv_tail], ingest_settings, capsys)
    assert code == 1 and out == "" and message in err
    assert "Nguyen" not in err and NAME not in err and str(phone_file.parent) not in err
    assert _recordings(ingest_settings) == []


def test_t_io_19_an_unreadable_file_exits_with_1_without_its_name(ingest_settings, truncated_video, tmp_path, capsys):
    bad = tmp_path / NAME
    shutil.copyfile(truncated_video, bad)
    code, out, err = run(["ingest", str(bad), *IDS], ingest_settings, capsys)
    assert code == 1 and out == "" and "could not read" in err
    assert NAME not in err and "Nguy" not in err and str(tmp_path) not in err


@pytest.mark.parametrize(
    "argv",
    [
        ["ingest", "x.mp4", "--participant", "P03", "--session", "S01", "--camera", "camA"],  # no --take
        ["ingest", "x.mp4", "--session", "S01", "--take", "S01-P03-T02", "--camera", "camA"],  # no --participant
        ["ingest", "x.mp4", "--participant", "P03", "--take", "S01-P03-T02", "--camera", "camA"],  # no --session
        ["ingest", "x.mp4", "--participant", "P03", "--session", "S01", "--take", "S01-P03-T02"],  # no --camera
        ["ingest", "--participant", "P03", "--session", "S01", "--take", "S01-P03-T02", "--camera", "camA"],  # no file
        ["ingest", "x.mp4", *IDS, "--camera-height-m", "1.1"],  # capture value without --role
        ["ingest", "x.mp4", *IDS, "--role", "ceiling"],
        ["ingest", "x.mp4", *IDS, "--role", "main_axis", "--camera-height-m", "tall"],
    ],
    ids=[
        "no-take",
        "no-participant",
        "no-session",
        "no-camera",
        "no-file",
        "height-without-role",
        "bad-role",
        "bad-number",
    ],
)
def test_t_io_19_a_usage_error_exits_with_2_and_stores_nothing(ingest_settings, capsys, argv):
    with pytest.raises(SystemExit) as exc:
        main(argv, settings=ingest_settings)
    assert exc.value.code == 2
    capsys.readouterr()
    assert _recordings(ingest_settings) == []


def test_t_io_19_ingest_with_proxy_flag_creates_proxy(ingest_settings, phone_file, capsys):
    code, out, err = run(["ingest", str(phone_file), *IDS, "--proxy"], ingest_settings, capsys)
    assert code == 0
    [row] = _recordings(ingest_settings)
    rid = row["recording_id"]
    assert f"ingested {rid}" in out
    assert "proxy: 240p, check passed" in out

    rec_dir = ingest_settings.data_dir / "recordings" / rid
    assert (rec_dir / "proxy.mp4").is_file()
    assert (rec_dir / "proxy.json").is_file()


def test_t_io_19_proxy_command_remakes_proxy(ingest_settings, phone_file, capsys):
    # First ingest without proxy
    run(["ingest", str(phone_file), *IDS], ingest_settings, capsys)
    [row] = _recordings(ingest_settings)
    rid = row["recording_id"]
    rec_dir = ingest_settings.data_dir / "recordings" / rid
    assert not (rec_dir / "proxy.mp4").exists()

    # Now run `taiji proxy <rid>`
    code, out, err = run(["proxy", rid], ingest_settings, capsys)
    assert code == 0
    assert out.strip() == f"proxy {rid} (240p, check passed)"
    assert (rec_dir / "proxy.mp4").is_file()
    assert (rec_dir / "proxy.json").is_file()


def test_t_io_19_proxy_command_errors(ingest_settings, capsys):
    # Bad UUID format
    code, out, err = run(["proxy", "not-a-uuid"], ingest_settings, capsys)
    assert code == 1 and "UUID4" in err

    # Non-existent UUID
    missing_id = "3f2b8c1e-5d4a-4e7b-9c1a-0b2d3e4f5a6b"
    code, out, err = run(["proxy", missing_id], ingest_settings, capsys)
    assert code == 1 and "not found" in err

    # A valid UUID followed by a newline is not a UUID (the "$" of a regular expression accepts a trailing newline)
    code, out, err = run(["proxy", missing_id + "\n"], ingest_settings, capsys)
    assert code == 1 and "UUID4" in err

    # Usage error (no recording_id arg)
    with pytest.raises(SystemExit) as exc:
        main(["proxy"], settings=ingest_settings)
    assert exc.value.code == 2


def test_t_io_27_proxy_command_exits_1_when_the_timestamp_check_failed(ingest_settings, phone_file, capsys):
    run(["ingest", str(phone_file), *IDS], ingest_settings, capsys)
    [row] = _recordings(ingest_settings)
    rid = row["recording_id"]
    tamper_pts(ingest_settings.data_dir / "recordings" / rid, shift_s=0.2)  # 6 frames at 30 fps

    code, out, err = run(["proxy", rid], ingest_settings, capsys)

    assert code == 1
    assert out.strip() == f"proxy {rid} (240p, check failed)"  # the result is still printed: the proxy exists
    assert rid in err and "marked unusable" in err and "6.0 frames" in err
    rec_dir = ingest_settings.data_dir / "recordings" / rid
    assert (rec_dir / "proxy.mp4").is_file() and (rec_dir / "proxy.json").is_file()


def test_t_io_27_ingest_with_proxy_exits_1_when_the_proxy_failed_but_names_the_recording(
    ingest_settings, phone_file, capsys, monkeypatch
):
    def boom(_rec_dir):
        raise ProxyError("ffmpeg failed to encode the proxy video")

    monkeypatch.setattr(ingest_module, "make_proxy", boom)

    code, out, err = run(["ingest", str(phone_file), *IDS, "--proxy"], ingest_settings, capsys)

    [row] = _recordings(ingest_settings)  # the recording was stored
    rid = row["recording_id"]
    assert code == 1
    assert out.strip() == f"ingested {rid} (take S01-P03-T02, camA)"
    # standard error also carries the log lines of the console handler: look for the error line itself
    assert f"error: the proxy of {rid} was not made: ffmpeg failed to encode the proxy video" in err.splitlines()
    assert NAME not in out + err and str(phone_file.parent) not in out + err


def test_t_io_27_ingest_with_proxy_exits_1_when_the_timestamp_check_failed(
    ingest_settings, phone_file, capsys, monkeypatch
):
    run(["ingest", str(phone_file), *IDS], ingest_settings, capsys)  # first without a proxy
    [row] = _recordings(ingest_settings)
    rid = row["recording_id"]
    tamper_pts(ingest_settings.data_dir / "recordings" / rid, shift_s=0.2)

    code, out, err = run(["ingest", str(phone_file), *IDS, "--proxy"], ingest_settings, capsys)

    assert code == 1
    assert out.strip() == f"already ingested {rid} (proxy: 240p, check failed)"
    assert rid in err and "marked unusable" in err
