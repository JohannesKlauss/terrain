"""Synthetic stdio peer shaped like a Codex App Server. No model, network, account or child."""

import json
import os
import signal
import sys
import time
from pathlib import Path

ARGS = sys.argv[1:]
STATE = Path(ARGS[ARGS.index("--state") + 1]) / "threads.json"
IGNORE_TERM = "--ignore-term" in ARGS
threads = json.loads(STATE.read_text()) if STATE.is_file() else {}
served = iter(range(1, 1_000_000))


def save():
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(threads))
    os.replace(temporary, STATE)


def send(message):
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def receive():
    line = sys.stdin.readline()
    if not line:
        if IGNORE_TERM:
            time.sleep(30)
        sys.exit(0)
    return json.loads(line)


def call_host(method, params):
    request_id = f"srv-{next(served)}"
    send({"id": request_id, "method": method, "params": params})
    reply = receive()
    if reply.get("id") != request_id:
        sys.exit(4)
    return reply


def finish(thread_id, turn_id, status, text=None):
    if text is not None:
        item = {"type": "agentMessage", "id": f"{turn_id}-msg", "text": text}
        send({"method": "item/completed", "params": {"threadId": thread_id, "item": item}})
    threads[thread_id]["turns"].append({"id": turn_id, "status": status})
    save()
    turn = {"id": turn_id, "status": status}
    send({"method": "turn/completed", "params": {"threadId": thread_id, "turn": turn}})


# Fixed synthetic tool requests; "run_shell" is only a name the host must refuse.
CASES = {
    "allowed": ("stage_frame", {"component_id": "frame"}),
    "out_of_scope": ("stage_frame", {"component_id": "figure.body"}),
    "stale_base": ("stage_frame", {"component_id": "frame", "base_revision": "0" * 64}),
    "extra_field": ("stage_frame", {"component_id": "frame", "scale": 2}),
    "unregistered": ("run_shell", {"command": "true"}),
    "thread_mismatch": ("stage_frame", {"component_id": "frame"}),
    "stale_turn": ("stage_frame", {"component_id": "frame"}),
}


def turn(thread_id, turn_id, text):
    kind, _, rest = text.partition(":")
    if kind == "tool":
        case, _, digest = rest.partition(":")
        tool, arguments = CASES[case]
        if case != "stale_base":
            arguments = {"base_revision": digest} | arguments
        params = {
            "threadId": "thread-other" if case == "thread_mismatch" else thread_id,
            "turnId": "turn-old" if case == "stale_turn" else turn_id,
            "callId": f"{turn_id}-call",
            "tool": tool,
            "arguments": arguments,
        }
        reply = call_host("item/tool/call", params)
        finish(thread_id, turn_id, "completed", reply["result"]["contentItems"][0]["text"])
    elif kind == "requests":
        approval = call_host("item/commandExecution/requestApproval", {"threadId": thread_id})
        unknown = call_host("x/unknown", {"threadId": thread_id})
        summary = f"{approval['result']['decision']} {unknown['error']['code']}"
        finish(thread_id, turn_id, "completed", summary)
    elif kind == "unmatched":
        send({"id": 9999, "result": {}})
        send({"id": 1, "result": {}})
        finish(thread_id, turn_id, "completed", "done")
    elif kind == "crash":
        sys.exit(3)
    elif kind == "wait":
        return turn_id
    else:
        finish(thread_id, turn_id, "completed", "done")
    return None


def main():
    if IGNORE_TERM:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    active = None
    while True:
        message = receive()
        method, params = message.get("method"), message.get("params") or {}
        request_id = message.get("id")
        if method == "initialize":
            send({"id": request_id, "result": {"userAgent": "synthetic-app-server/0"}})
        elif method == "initialized":
            continue
        elif method == "thread/start":
            thread_id = f"thread-{len(threads) + 1}"
            threads[thread_id] = {"turns": []}
            save()
            send({"id": request_id, "result": {"thread": {"id": thread_id}}})
        elif method == "thread/resume" and params.get("threadId") in threads:
            thread = {"id": params["threadId"], "turns": threads[params["threadId"]]["turns"]}
            send({"id": request_id, "result": {"thread": thread}})
        elif method == "thread/resume":
            send({"id": request_id, "error": {"code": -32600, "message": "unknown thread"}})
        elif method == "turn/start":
            thread_id = params["threadId"]
            turn_id = f"turn-{sum(len(t['turns']) for t in threads.values()) + 1}"
            send({"id": request_id, "result": {"turn": {"id": turn_id, "status": "inProgress"}}})
            started = {"threadId": thread_id, "turn": {"id": turn_id, "status": "inProgress"}}
            send({"method": "turn/started", "params": started})
            waiting = turn(thread_id, turn_id, params["input"][0]["text"])
            active = (thread_id, turn_id) if waiting else None
        elif method == "turn/interrupt" and active and params.get("turnId") == active[1]:
            send({"id": request_id, "result": {}})
            # A late call after interrupt; the host must refuse it as stale.
            late = {"component_id": "frame", "base_revision": "late"}
            call_host(
                "item/tool/call",
                {
                    "threadId": active[0],
                    "turnId": active[1],
                    "callId": "late",
                    "tool": "stage_frame",
                    "arguments": late,
                },
            )
            finish(*active, "interrupted")
            active = None
        elif request_id is not None:
            send({"id": request_id, "error": {"code": -32601, "message": "unsupported"}})


if __name__ == "__main__":
    main()
