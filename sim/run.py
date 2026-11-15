"""`make sim`: broker, simulated body and orchestrator on this machine, without hardware.

    python -m sim [--script sim/scripts/dos-entradas.yaml] [--greeting-window-min 10]
        [--out .sim]

Starts a throwaway test broker (deploy/broker/local.py), the brain, and the simulated
body playing the script; prints what crosses the bus and a summary. Logs and traces
stay in `.sim/<UTC time>/`; the broker's passwords live in a temporary directory that
is deleted at the end.
"""

import argparse
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from contracts.bus import Message
from contracts.topics import health_topic
from contracts.traces import TraceRecord, read_traces
from deploy.broker.local import PULL_HINT, LocalBroker, broker_available
from sim.script import load_script

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCRIPT = ROOT / "sim" / "scripts" / "dos-entradas.yaml"
START_TIMEOUT_S = 20


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
    def ok(self) -> bool:
        return all(code == 0 for code in self.exit_codes.values())


def _describe(message: Message) -> str:
    fields = message.payload.model_dump(mode="json", exclude_none=True)
    shown = {k: v for k, v in fields.items() if k not in ("first_seen_ts", "frame_ts", "bbox")}
    return " ".join(f"{k}={v}" for k, v in shown.items())


class _Monitor:
    def __init__(self, result: SimResult, quiet: bool):
        self.result, self.quiet = result, quiet
        self.start = time.monotonic()
        self.changed = threading.Condition()

    def __call__(self, message: Message) -> None:
        with self.changed:
            self.result.messages.append(message)
            self.changed.notify_all()
        if not self.quiet:
            elapsed = time.monotonic() - self.start
            print(f"  +{elapsed:6.2f} s  {message.topic:<40} {_describe(message)}", flush=True)

    def wait_for(self, predicate, timeout_s: float) -> bool:
        with self.changed:
            return self.changed.wait_for(
                lambda: any(predicate(m) for m in self.result.messages), timeout_s
            )


def _spawn(args: list[str], log: Path) -> subprocess.Popen:
    with log.open("w") as out:
        return subprocess.Popen(
            [sys.executable, *args], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT
        )


def _stop(process: subprocess.Popen, timeout_s: float = 10) -> int | None:
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout_s)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            return None
    return process.returncode


def _online(component: str):
    topic = health_topic(component)
    return lambda m: m.topic == topic and m.payload.status == "online"


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
    traces = run_dir / "traces"
    run_dir.mkdir(parents=True)
    result = SimResult(run_dir)
    monitor = _Monitor(result, quiet)
    with tempfile.TemporaryDirectory(prefix="sancho-sim-") as tmp:
        broker = LocalBroker(Path(tmp) / "broker", "test")
        processes: dict[str, subprocess.Popen] = {}
        try:
            with broker.service("recorder") as recorder:
                recorder.subscribe("sancho/#", monitor)
                port = str(broker.port)
                brain_args = ["-m", "brain", "--port", port, "--traces", str(traces),
                              "--password-file", str(broker.credential_file("brain"))]  # fmt: skip
                if greeting_window_min is not None:
                    brain_args += ["--greeting-window-min", str(greeting_window_min)]
                processes["brain"] = _spawn(brain_args, run_dir / "brain.log")
                if not monitor.wait_for(_online("brain"), START_TIMEOUT_S):
                    raise RuntimeError(f"brain did not come online; see {run_dir / 'brain.log'}")
                processes["sim"] = _spawn(
                    ["-m", "sim.body", "--port", port, "--traces", str(traces),
                     "--password-file", str(broker.credential_file("sim")),
                     "--script", str(script_path), "--exit-after-script",
                     "--synth-ms", str(synth_ms), "--speech-ms", str(speech_ms),
                     "--linger-ms", str(linger_ms)],
                    run_dir / "sim.log",
                )  # fmt: skip
                budget = START_TIMEOUT_S + script.duration_ms / 1000 + linger_ms / 1000 + 30
                try:
                    processes["sim"].wait(budget)
                except subprocess.TimeoutExpired:
                    pass
                for name, process in processes.items():
                    result.exit_codes[name] = _stop(process)
                time.sleep(0.2)  # let the final health messages arrive
        finally:
            for process in processes.values():
                if process.poll() is None:
                    process.kill()
            broker.stop()
            if broker.log.exists():
                shutil.copy(broker.log, run_dir / "broker.log")
    for path in sorted(traces.glob("brain-*.jsonl")):
        result.decisions += [t for t in read_traces(path) if t.kind == "decision"]
    for path in sorted(traces.glob("sim-*.jsonl")):
        result.actions += read_traces(path)
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
    lines += [f"  códigos de salida: {codes}", f"  logs y trazas: {result.run_dir}"]
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
