"""`make replay`: replays a recording to a fresh orchestrator and compares decisions.

    python -m sim.rerun RECORDING [--traces DIR] [--greeting-window-min N] [--out .sim]

Starts a clean test broker and the brain, publishes the recording with the `replay`
role (sim/replay.py) and compares the brain's decision traces with the original ones
as docs/contratos/grabaciones.md says: same order, `name`, `decision` and
`inputs.message_ids`. By default the original traces are the `traces/` next to the
recording, which is how `make sim` leaves them. Give the brain the configuration of
the original session (for example `--greeting-window-min`).
"""

import argparse
import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from contracts.recordings import read_recording
from contracts.traces import TraceRecord
from deploy.broker.local import PULL_HINT, broker_available
from sim.processes import ROOT, Session, decision_key, read_component_traces
from sim.replay import play

SETTLE_S = 1.0  # after the last replayed message, time for the brain to decide


@dataclass
class RerunResult:
    run_dir: Path
    replayed: int
    decisions: list[TraceRecord]
    exit_code: int | None


def decisions_in(traces: Path) -> list[TraceRecord]:
    return [t for t in read_component_traces(traces, "brain") if t.kind == "decision"]


def rerun(recording: Path, out: Path, *, config: dict | None = None) -> RerunResult:
    lines = read_recording(recording)  # fail before starting anything
    run_dir = out / ("replay-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ"))
    with Session(run_dir, record=False) as session:
        session.start_brain(config)
        with session.broker.service("replay") as replay:
            replayed = play(replay, lines, threading.Event())
        time.sleep(SETTLE_S)
        code = session.stop("brain")
    return RerunResult(run_dir, replayed, decisions_in(session.traces), code)


def differences(original: list[TraceRecord], replayed: list[TraceRecord]) -> list[str]:
    a, b = [decision_key(t) for t in original], [decision_key(t) for t in replayed]
    found = []
    for i in range(max(len(a), len(b))):
        left = a[i] if i < len(a) else None
        right = b[i] if i < len(b) else None
        if left != right:
            found.append(f"decisión {i + 1}: original {left} / reproducción {right}")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sim.rerun",
                                     description=__doc__.split("\n")[0])  # fmt: skip
    parser.add_argument("recording", type=Path)
    parser.add_argument("--traces", type=Path, help="original traces (default: next to it)")
    parser.add_argument("--greeting-window-min", type=float)
    parser.add_argument("--out", type=Path, default=ROOT / ".sim")
    args = parser.parse_args(argv)
    if not broker_available():
        print(f"make replay necesita el broker: ejecuta `{PULL_HINT}` o define MOSQUITTO",
              file=sys.stderr)  # fmt: skip
        return 2
    original_dir = args.traces or args.recording.parent / "traces"
    original = decisions_in(original_dir)
    config = {}
    if args.greeting_window_min is not None:
        config["greeting_window_min"] = args.greeting_window_min
    result = rerun(args.recording, args.out, config=config)
    diff = differences(original, result.decisions)
    print(f"Reproducción de {args.recording}")
    print(f"  mensajes reproducidos: {result.replayed}")
    print(f"  decisiones: original {len(original)}, reproducción {len(result.decisions)}")
    for trace in result.decisions:
        print(f"    - {trace.decision}: {trace.reason}")
    if diff:
        print("  DISTINTAS:")
        print("\n".join(f"    {line}" for line in diff))
    else:
        print("  Mismas decisiones (orden, regla, decisión y mensajes de entrada).")
    print(f"  logs y trazas: {result.run_dir}")
    return 0 if not diff and result.exit_code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
