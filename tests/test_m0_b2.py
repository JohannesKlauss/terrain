import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).parents[1] / "examples" / "m0_b2"
ENTRY = EXAMPLE / "run.py"


@pytest.fixture
def b2(monkeypatch):
    monkeypatch.syspath_prepend(str(EXAMPLE))
    import native_host
    import run

    return native_host, run


def test_entry_point_passes_every_simulated_scenario():
    result = subprocess.run(
        [sys.executable, ENTRY], capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["hosted_requests"] == 0
    assert "simulated" in report["route"]
    assert set(report["scenarios"]) == {
        "correlation",
        "refusals",
        "cancellation",
        "forced_reap",
        "crash_and_resume",
        "failed_recovery",
    }
    assert all(scenario["passed"] for scenario in report["scenarios"].values())
    assert report["scenarios"]["forced_reap"]["reap"] == {"how": "sigkill", "returncode": -9}


def test_entry_point_accepts_no_worker_or_provider_input():
    result = subprocess.run(
        [sys.executable, ENTRY, "--worker", "/bin/sh"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_matrix_reports_failure_when_an_expectation_is_wrong(b2, monkeypatch, capsys):
    _, run = b2
    monkeypatch.setitem(run.REFUSALS, "stale_base", "allowed")
    assert run.main([]) == 1
    report = json.loads(capsys.readouterr().out)
    assert not report["scenarios"]["refusals"]["passed"]


def test_host_only_launches_the_bundled_stub(b2, tmp_path):
    native_host, run = b2
    with pytest.raises(ValueError):
        native_host.NativeHost(run.ACCEPTED, tmp_path, ["--state", "/"])


def test_resume_must_match_the_app_journal(b2, tmp_path):
    native_host, run = b2
    session = native_host.NativeHost(run.ACCEPTED, tmp_path)
    try:
        session.connect()
        session.start_thread()
        session.run_turn("plain")
        with pytest.raises(native_host.RecoveryFailed):
            session.recover("turn-unknown")
        assert session.process is None
        assert session.accepted == run.ACCEPTED
        assert [reap["how"] for reap in session.reaps] == ["exited", "exited"]
    finally:
        session.close()


def test_reader_flags_oversized_and_invalid_lines(b2):
    native_host, _ = b2
    inbox = native_host.queue.Queue()
    big = b'{"id":1,"result":"' + b"x" * native_host.MAX_LINE + b'"}\n'
    native_host.NativeHost._read(None, BytesIO(big + b"not json\n[]\n"), inbox)
    messages = [inbox.get_nowait() for _ in range(4)]
    assert messages[:3] == [
        {"_violation": "oversized_line"},
        {"_violation": "invalid_json"},
        {"_violation": "not_object"},
    ]
    assert messages[3] is native_host.EOF_MARK


def test_recovery_reaps_a_worker_that_dies_at_startup(b2, tmp_path):
    native_host, run = b2
    session = native_host.NativeHost(run.ACCEPTED, tmp_path)
    try:
        session.connect()
        session.start_thread()
        known, _ = session.run_turn("plain")
        (tmp_path / "threads.json").write_text("not json")
        with pytest.raises(native_host.RecoveryFailed):
            session.recover(known)
        assert session.process is None
        assert [reap["how"] for reap in session.reaps] == ["exited", "exited"]
        assert session.reaps[1]["returncode"] != 0
        assert not session.staged
        assert session.accepted == run.ACCEPTED
    finally:
        session.close()


@pytest.mark.parametrize("turns", ["not-a-list", [{"id": "turn-1"}], [7]])
def test_recovery_rejects_a_malformed_resume_result(b2, tmp_path, turns):
    native_host, run = b2
    session = native_host.NativeHost(run.ACCEPTED, tmp_path)
    try:
        session.connect()
        session.start_thread()
        known, _ = session.run_turn("plain")
        (tmp_path / "threads.json").write_text(json.dumps({session.thread_id: {"turns": turns}}))
        with pytest.raises(native_host.RecoveryFailed):
            session.recover(known)
        assert session.process is None
        assert [reap["how"] for reap in session.reaps] == ["exited", "exited"]
        assert session.server_requests == []
        assert session.accepted == run.ACCEPTED
    finally:
        session.close()


def test_late_response_after_timeout_is_flagged(b2, tmp_path):
    native_host, run = b2
    session = native_host.NativeHost(run.ACCEPTED, tmp_path)
    try:
        session.connect()
        with pytest.raises(native_host.ProtocolError, match="timed out"):
            session.request("x/slow", {}, timeout=0)
        assert session.pending == {}
        session.start_thread()
        assert session.violations == [{"kind": "unmatched_response", "id": 2}]
        assert session.responses == {}
    finally:
        session.close()
