"""Starting, watching and stopping components, shared by `make sim`, replay and the bench."""

import logging
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

from contracts.bus import Message
from contracts.topics import health_topic
from contracts.traces import TraceRecord, read_traces
from deploy.broker.local import LocalBroker
from sim.recorder import Recorder

ROOT = Path(__file__).resolve().parent.parent
START_TIMEOUT_S = 20


def describe(message: Message) -> str:
    fields = message.payload.model_dump(mode="json", exclude_none=True)
    shown = {k: v for k, v in fields.items() if k not in ("first_seen_ts", "frame_ts", "bbox")}
    return " ".join(f"{k}={v}" for k, v in shown.items())


class Watch:
    """A validated handler that keeps every message and lets you wait for one."""

    def __init__(self, *, echo: bool = False):
        self.messages: list[Message] = []
        self.echo = echo
        self.start = time.monotonic()
        self._changed = threading.Condition()

    def __call__(self, message: Message) -> None:
        with self._changed:
            self.messages.append(message)
            self._changed.notify_all()
        if self.echo:
            elapsed = time.monotonic() - self.start
            print(f"  +{elapsed:6.2f} s  {message.topic:<40} {describe(message)}", flush=True)

    def wait_for(
        self, predicate: Callable[[Message], bool], timeout_s: float, *, since: int = 0
    ) -> bool:
        """Waits for a message matching `predicate` among those after the first `since`."""
        with self._changed:
            return self._changed.wait_for(
                lambda: any(predicate(m) for m in self.messages[since:]), timeout_s
            )


def online(component: str) -> Callable[[Message], bool]:
    topic = health_topic(component)
    return lambda m: m.topic == topic and m.payload.status == "online"


def spawn(args: list[str], log: Path) -> subprocess.Popen:
    """Runs `python <args>` from the repo root with its output in `log`."""
    with log.open("a") as out:
        return subprocess.Popen(
            [sys.executable, *args], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT
        )


def stop(process: subprocess.Popen, *, abrupt: bool = False, timeout_s: float = 10) -> int | None:
    """SIGTERM (clean close) or SIGKILL (abrupt). Returns the exit code, None if it hung."""
    if process.poll() is None:
        process.send_signal(signal.SIGKILL if abrupt else signal.SIGTERM)
        try:
            process.wait(timeout_s)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            return None
    return process.returncode


def brain_args(broker: LocalBroker, traces: Path, config: dict | None = None) -> list[str]:
    args = ["-m", "brain", "--port", str(broker.port), "--traces", str(traces),
            "--password-file", str(broker.credential_file("brain"))]  # fmt: skip
    for key, value in (config or {}).items():
        args += [f"--{key.replace('_', '-')}", str(value)]
    return args


def sim_body_args(broker: LocalBroker, traces: Path, *extra: str) -> list[str]:
    return ["-m", "sim.body", "--port", str(broker.port), "--traces", str(traces),
            "--password-file", str(broker.credential_file("sim")), *extra]  # fmt: skip


def read_component_traces(traces: Path, component: str) -> list[TraceRecord]:
    records = []
    for path in sorted(Path(traces).glob(f"{component}-*.jsonl")):
        records += read_traces(path)
    return records


def decision_key(trace: TraceRecord) -> tuple:
    """What grabaciones.md compares between two runs (not `outputs`: they are new)."""
    return (trace.name, trace.decision, tuple(trace.inputs.message_ids))


class Session:
    """A clean bus for one run: a fresh test broker (no retained messages), an observer
    with the `recorder` role that keeps every message (and, optionally, a recording),
    and the components started in it. Everything is stopped on exit; the broker's
    passwords live in a temporary directory that is deleted."""

    def __init__(self, run_dir: Path, *, echo: bool = False, record: bool = True):
        self.run_dir = Path(run_dir)
        self.echo, self.record = echo, record
        self.processes: dict[str, subprocess.Popen] = {}
        self.exit_codes: dict[str, int | None] = {}
        self.watch = Watch(echo=echo)
        self.recorder = None

    def __enter__(self) -> "Session":
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(prefix="sancho-session-")
        self.broker = None
        try:
            self.broker = LocalBroker(Path(self._tmp.name) / "broker", "test")
            # The observer sees invalid messages too; logging them is the components' job.
            quiet = logging.getLogger("sancho.session.observer")
            quiet.setLevel(logging.ERROR)
            self.observer = self.broker.service("recorder", logger=quiet).connect()
            if self.record:
                self.recorder = Recorder(self.run_dir / "recording.jsonl")
                self.observer.subscribe_raw("sancho/#", self.recorder)
            self.observer.subscribe("sancho/#", self.watch)
        except BaseException:
            if self.broker:
                self.broker.stop()
            self._tmp.cleanup()
            raise
        return self

    @property
    def traces(self) -> Path:
        return self.run_dir / "traces"

    def start(self, name: str, args: list[str]) -> subprocess.Popen:
        process = spawn(args, self.run_dir / f"{name}.log")
        self.processes[name] = process
        return process

    def start_brain(self, config: dict | None = None, *, wait: bool = True) -> None:
        since = len(self.watch.messages)
        self.start("brain", brain_args(self.broker, self.traces, config))
        if wait:
            self.wait_online("brain", since)

    def start_sim_body(self, *extra: str, wait: bool = True) -> None:
        since = len(self.watch.messages)
        self.start("sim", sim_body_args(self.broker, self.traces, *extra))
        if wait:
            self.wait_online("body", since)

    def wait_online(self, component: str, since: int) -> None:
        """Waits for an `online` of `component` after the first `since` messages."""
        if not self.watch.wait_for(online(component), START_TIMEOUT_S, since=since):
            raise RuntimeError(f"{component} did not come online; see {self.run_dir}")

    def stop(self, name: str, *, abrupt: bool = False) -> int | None:
        code = stop(self.processes[name], abrupt=abrupt)
        self.exit_codes[name] = code
        return code

    def __exit__(self, *exc) -> None:
        try:
            for name, process in self.processes.items():
                if process.poll() is None:
                    self.exit_codes[name] = stop(process)
                else:
                    self.exit_codes.setdefault(name, process.returncode)
            time.sleep(0.2)  # let the last health messages arrive
            self.observer.close()
        finally:
            if self.recorder:
                self.recorder.close()
            self.broker.stop()
            if self.broker.log.exists():
                shutil.copy(self.broker.log, self.run_dir / "broker.log")
            self._tmp.cleanup()
