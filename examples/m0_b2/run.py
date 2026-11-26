"""Run the simulated native-protocol matrix against the bundled stub. Takes no arguments."""

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from native_host import Accepted, NativeHost, RecoveryFailed, WorkerExited

ACCEPTED = Accepted(hashlib.sha256(b"m0-b2 synthetic accepted scene").hexdigest(), "preview-v1")
APPROVAL = "item/commandExecution/requestApproval"
REFUSALS = {
    "out_of_scope": "out_of_scope",
    "stale_base": "stale_base",
    "extra_field": "invalid_arguments",
    "unregistered": "unregistered_tool",
    "thread_mismatch": "thread_mismatch",
    "stale_turn": "stale_turn",
}


def host(root, name, *options):
    state = root / name
    state.mkdir(exist_ok=True)
    return NativeHost(ACCEPTED, state, options)


def correlation(root):
    session = host(root, "correlation")
    try:
        session.connect()
        session.start_thread()
        _, status = session.run_turn(f"tool:allowed:{ACCEPTED.digest}")
        _, unmatched = session.run_turn("unmatched")
        _, requests = session.run_turn("requests")
        message = session.notifications
        ordered = message.index("turn/started") < message.index("item/completed")
        return {
            "passed": status == unmatched == requests == "completed"
            and ordered
            and [entry["verdict"] for entry in session.tool_log] == ["allowed"]
            and len(session.staged) == 1
            and [v["id"] for v in session.violations] == [9999, 1]
            and session.server_requests[-2:] == [APPROVAL, "x/unknown"],
            "violations": session.violations,
        }
    finally:
        session.close()


def refusals(root):
    session = host(root, "refusals")
    try:
        session.connect()
        session.start_thread()
        for case in REFUSALS:
            session.run_turn(f"tool:{case}:{ACCEPTED.digest}")
        logged = zip(REFUSALS, session.tool_log, strict=True)
        reasons = {case: entry.get("reason") for case, entry in logged}
        return {"passed": reasons == REFUSALS and not session.staged, "reasons": reasons}
    finally:
        session.close()


def cancellation(root):
    session = host(root, "cancellation")
    session.connect()
    session.start_thread()
    session.start_turn("wait")
    status = session.interrupt()
    reap = session.close()
    late = session.tool_log[-1]
    return {
        "passed": status == "interrupted"
        and late
        == {"callId": "late", "tool": "stage_frame", "verdict": "refused", "reason": "stale_turn"}
        and not session.staged
        and reap["how"] == "exited",
        "reap": reap,
    }


def forced_reap(root):
    session = host(root, "forced", "--ignore-term")
    session.connect()
    session.start_thread()
    reap = session.close(grace=1)
    return {"passed": reap["how"] == "sigkill", "reap": reap}


def crash_and_resume(root):
    session = host(root, "resume")
    try:
        session.connect()
        session.start_thread()
        known, _ = session.run_turn(f"tool:allowed:{ACCEPTED.digest}")
        crashed = session.start_turn("crash")
        try:
            session.wait_turn(crashed)
        except WorkerExited:
            exited = True
        else:
            exited = False
        session.recover(known)
        _, after = session.run_turn(f"tool:allowed:{ACCEPTED.digest}")
        return {
            "passed": exited
            and after == "completed"
            and session.reaps[0]["returncode"] == 3
            and len(session.staged) == 2
            and session.accepted == ACCEPTED,
            "reaps": session.reaps,
        }
    finally:
        session.close()


def failed_recovery(root):
    session = host(root, "lost-state")
    session.thread_id = "thread-1"
    try:
        session.recover("turn-1")
    except RecoveryFailed:
        failed = True
    else:
        failed = False
    return {
        "passed": failed
        and session.process is None
        and session.server_requests == []
        and not session.staged
        and session.accepted == ACCEPTED,
        "reaps": session.reaps,
    }


SCENARIOS = (correlation, refusals, cancellation, forced_reap, crash_and_resume, failed_recovery)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="terrain-m0-b2-") as root:
        results = {scenario.__name__: scenario(Path(root)) for scenario in SCENARIOS}
    report = {
        "route": "synthetic stdio stub; simulated, not Codex",
        "hosted_requests": 0,
        "accepted_digest": ACCEPTED.digest,
        "scenarios": results,
    }
    print(json.dumps(report, indent=2))
    return 0 if all(result["passed"] for result in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
