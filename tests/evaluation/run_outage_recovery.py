"""Capture a failure-and-recovery trace of the workflow against the real model.

    python tests/evaluation/run_outage_recovery.py

The workflow is pointed at a local port with nothing listening, so its first
check fails as SERVICE_UNAVAILABLE. While the workflow waits before its retry,
a forwarder to the real model server is started on that port: from the
workflow's side, the server has come back. The retry then reaches the model
and the run carries on to its report.

The outage is induced, and the trace says so in its name. Everything after it
is real: the retry, the check by the real model, the report and the hand-off.
The trace and the log are written to evidence/traces/workflow/.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
TRACE_DIR = REPO_ROOT / "evidence" / "traces" / "workflow"
DEFAULT_UPSTREAM = "http://localhost:11434"
DEFAULT_NAME = "live-02-outage-retried-and-recovered"
BUFFER_BYTES = 65536
LOOPBACK = "127.0.0.1"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((LOOPBACK, 0))
        return probe.getsockname()[1]


def _pump(source: socket.socket, destination: socket.socket) -> None:
    try:
        while data := source.recv(BUFFER_BYTES):
            destination.sendall(data)
    except OSError:
        pass
    finally:
        for end in (source, destination):
            try:
                end.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _forward(listener: socket.socket, upstream: tuple[str, int]) -> None:
    while True:
        try:
            client, _address = listener.accept()
        except OSError:
            return
        try:
            server = socket.create_connection(upstream)
        except OSError:
            client.close()
            continue
        threading.Thread(target=_pump, args=(client, server), daemon=True).start()
        threading.Thread(target=_pump, args=(server, client), daemon=True).start()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--submission", type=Path,
                        default=REPO_ROOT / "knowledge" / "samples" / "synthetic-submission.txt")
    parser.add_argument("--checklist", type=Path, default=TRACE_DIR / "live-checklist.txt")
    parser.add_argument("--name", default=DEFAULT_NAME, help="File name of the trace and log, no extension")
    parser.add_argument("--outage-seconds", type=float, default=15.0,
                        help="How long the model server stays unreachable")
    parser.add_argument("--retry-delay", type=float, default=45.0,
                        help="The workflow's wait before its retry; longer than the outage")
    args = parser.parse_args()
    if args.retry_delay <= args.outage_seconds:
        parser.error("--retry-delay must be longer than --outage-seconds, or the retry also fails")

    target = urlparse(os.getenv("PROCURECHECK_BASE_URL", DEFAULT_UPSTREAM))
    upstream = (target.hostname or "localhost", target.port or 11434)
    port = _free_port()
    trace = TRACE_DIR / f"{args.name}.json"
    log = TRACE_DIR / f"{args.name}.log"
    command = [
        sys.executable, str(REPO_ROOT / "run.py"), "workflow",
        "--submission", str(args.submission), "--checklist", str(args.checklist),
        "--retry-delay", str(args.retry_delay), "--no-memory", "--trace", str(trace),
    ]
    environment = {**os.environ, "PROCURECHECK_BASE_URL": f"http://{LOOPBACK}:{port}"}

    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Model server unreachable at {LOOPBACK}:{port} for {args.outage_seconds:.0f}s, "
          f"then forwarded to {upstream[0]}:{upstream[1]}.")
    with log.open("w", encoding="utf-8") as output:
        output.write(
            f"Induced outage: nothing listens on {LOOPBACK}:{port} for the first "
            f"{args.outage_seconds:.0f} seconds; the workflow waits {args.retry_delay:.0f} seconds "
            f"before its retry.\n"
        )
        output.flush()
        workflow = subprocess.Popen(command, cwd=str(REPO_ROOT), env=environment,
                                    stdout=output, stderr=subprocess.STDOUT)
        time.sleep(args.outage_seconds)
        listener = socket.create_server((LOOPBACK, port))
        threading.Thread(target=_forward, args=(listener, upstream), daemon=True).start()
        print("Model server reachable again. Waiting for the workflow to finish.")
        code = workflow.wait()
        listener.close()
    print(f"Workflow exited with {code}. Trace: {trace}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
