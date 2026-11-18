"""`make sim`: broker, simulated body and orchestrator on this machine, without hardware.

    python -m sim [--script sim/scripts/dos-entradas.yaml] [--greeting-window-min 10]
        [--out .sim]

Starts a throwaway test broker (deploy/broker/local.py), the brain, and the simulated
body playing the script; prints what crosses the bus and a summary. Logs, traces and
the recording of the session (`recording.jsonl`, for `make replay`) stay in
`.sim/<UTC time>/`; the broker's passwords live in a temporary directory that is
deleted at the end.
"""

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from contracts.bus import Message
from contracts.traces import TraceRecord
from deploy.broker.local import PULL_HINT, broker_available
from sim.processes import ROOT, START_TIMEOUT_S, Session, read_component_traces
from sim.script import load_script

DEFAULT_SCRIPT = ROOT / "sim" / "scripts" / "dos-entradas.yaml"


@dataclass
class SimResult:
    run_dir: Path
    messages: list[Message] = field(default_factory=list)
    decisions: list[TraceRecord] = field(default_factory=list)
    actions: list[TraceRecord] = field(default_factory=list)
    exit_codes: dict[str, int | None] = field(default_factory=dict)

    def on(self, topic: str) -> list[Message]:
        return [m for m in self.messages if m.topic == topic]

    @property
    def recording(self) -> Path:
        return self.run_dir / "recording.jsonl"

    @property
    def ok(self) -> bool:
        return all(code == 0 for code in self.exit_codes.values())


def simulate(
    script_path: Path,
    out: Path,
    *,
    greeting_window_min: float | None = None,
    synth_ms: int = 200,
    speech_ms: int = 1000,
    linger_ms: int = 2000,
    quiet: bool = False,
) -> SimResult:
    script = load_script(script_path)  # fail before starting anything
    run_dir = out / datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    config = {} if greeting_window_min is None else {"greeting_window_min": greeting_window_min}
    with Session(run_dir, echo=not quiet) as session:
        session.start_brain(config)
        session.start_sim_body(
            "--script", str(script_path), "--exit-after-script", "--synth-ms", str(synth_ms),
            "--speech-ms", str(speech_ms), "--linger-ms", str(linger_ms),
        )  # fmt: skip
        budget = START_TIMEOUT_S + script.duration_ms / 1000 + linger_ms / 1000 + 30
        try:
            session.processes["sim"].wait(budget)
        except subprocess.TimeoutExpired:
            pass
        session.stop("sim")
        session.stop("brain")
    result = SimResult(run_dir, session.watch.messages, exit_codes=session.exit_codes)
    result.decisions = [t for t in read_component_traces(session.traces, "brain")
                        if t.kind == "decision"]  # fmt: skip
    result.actions = read_component_traces(session.traces, "sim")
    return result


def summary(result: SimResult) -> str:
    entered = result.on("sancho/body/vision/evt/person_entered")
    says = result.on("sancho/body/speech/cmd/say")
    statuses = result.on("sancho/body/speech/evt/status")
    started = {m.envelope.trace_id: m for m in statuses if m.payload.state == "started"}
    finished = [m for m in statuses if m.payload.state == "finished"]
    lines = [
        "Resumen de la simulación",
        f"  entradas: {len(entered)}   saludos: {len(says)}   "
        f"started: {len(started)}   finished: {len(finished)}",
        f"  decisiones con traza: {len(result.decisions)}",
    ]
    for trace in result.decisions:
        lines.append(f"    - {trace.decision}: {trace.reason}")
    for event in entered:
        start = started.get(event.envelope.trace_id)
        if start:
            latency = (start.envelope.ts - event.envelope.ts).total_seconds() * 1000
            lines.append(f"  {event.payload.track_id}: entrada → started en {latency:.0f} ms")
    codes = ", ".join(f"{name} {code}" for name, code in result.exit_codes.items())
    lines += [f"  códigos de salida: {codes}", f"  logs, trazas y grabación: {result.run_dir}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sim", description=__doc__.split("\n")[0])
    parser.add_argument("--script", type=Path, default=DEFAULT_SCRIPT)
    parser.add_argument("--greeting-window-min", type=float)
    parser.add_argument("--out", type=Path, default=ROOT / ".sim")
    args = parser.parse_args(argv)
    if not broker_available():
        print(f"make sim necesita el broker: ejecuta `{PULL_HINT}` o define MOSQUITTO",
              file=sys.stderr)  # fmt: skip
        return 2
    print(f"Simulación con {args.script}")
    result = simulate(args.script, args.out, greeting_window_min=args.greeting_window_min)
    print(summary(result))
    return 0 if result.ok else 1
