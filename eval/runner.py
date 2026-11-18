"""Evaluation bench (T11): runs the cases of eval/cases/ against the real components.

    python -m eval [--cases eval/cases] [--only CASE_ID] [--results eval/results]
        [--no-save]

Each case starts from a clean state (docs/contratos/casos-banco.md): a fresh test
broker without retained messages, the brain with `given.config`, and the simulated
body. The runner, with the `eval` role, executes `when`, watches every message on
`sancho/#` and checks `expect` and `forbid`. Results go to eval/results/ with the date
and the commit, to be versioned.
"""

import argparse
import json
import platform
import subprocess
import sys
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from brain.greeter import BrainConfig
from contracts.cases import CASES_VERSION, Case, Expectation, Prohibition, Step, load_case
from contracts.envelope import ENVELOPE_VERSION
from contracts.service import BusService
from contracts.topics import spec_for
from contracts.types import format_timestamp, utc_now
from deploy.broker.local import PULL_HINT, broker_available
from sim.processes import ROOT, Session

CASES_DIR = ROOT / "eval" / "cases"
RESULTS_DIR = ROOT / "eval" / "results"
WORK_DIR = ROOT / ".sim" / "bench"
# Components a case can stop and start, and the process that plays each one here.
COMPONENTS = {"brain": "brain", "body": "sim"}
SIM_BODY_ARGS = ("--synth-ms", "50", "--speech-ms", "200")


@dataclass(frozen=True)
class Observed:
    t_ms: float  # since the start of the case
    topic: str
    retained: bool
    message: dict | None  # None if not a JSON object


@dataclass
class Check:
    kind: str  # expect | forbid
    topic: str
    within_ms: int
    payload: dict | None
    limit: int  # expect: at least this many; forbid: no more than this many
    observed: int = 0
    ok: bool = False


@dataclass
class CaseResult:
    id: str
    file: str
    result: str  # pass | fail | error
    duration_ms: float
    checks: list[Check] = field(default_factory=list)
    error: str | None = None


# --- verification -----------------------------------------------------------------


def matches(expected: dict | None, observed: Observed) -> bool:
    """Partial match on the payload: the given fields must be equal, others ignored."""
    if expected is None:
        return True
    payload = (observed.message or {}).get("payload")
    if not isinstance(payload, dict):
        return False
    return all(key in payload and payload[key] == value for key, value in expected.items())


def count(rule: Expectation | Prohibition, observed: list[Observed]) -> int:
    return sum(
        1
        for o in observed
        if o.topic == rule.topic
        and not o.retained
        and 0 <= o.t_ms <= rule.within_ms
        and matches(rule.payload, o)
    )


def verify(case: Case, observed: list[Observed]) -> list[Check]:
    checks = []
    for rule in case.expect:
        n = count(rule, observed)
        checks.append(Check("expect", rule.topic, rule.within_ms, rule.payload, rule.count,
                            n, n >= rule.count))  # fmt: skip
    for rule in case.forbid:
        n = count(rule, observed)
        checks.append(Check("forbid", rule.topic, rule.within_ms, rule.payload, rule.count_gt,
                            n, n <= rule.count_gt))  # fmt: skip
    return checks


def duration_ms(case: Case) -> int:
    rules = [*case.expect, *case.forbid]
    return max([r.within_ms for r in rules] + [s.at_ms for s in case.when])


# --- execution --------------------------------------------------------------------


def envelope_for(topic: str, payload: dict[str, Any]) -> bytes:
    """A valid envelope around a payload that is NOT validated (casos-banco.md)."""
    spec = spec_for(topic)
    envelope = {
        "v": ENVELOPE_VERSION,
        "id": str(uuid.uuid4()),
        "ts": format_timestamp(utc_now()),
        "source": "eval",
        "type": spec.type if spec else "unknown",
        "trace_id": str(uuid.uuid4()),
        "payload": payload,
    }
    return json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode()


class _Observer:
    def __init__(self):
        self.start: float | None = None
        self.items: list[Observed] = []
        self._lock = threading.Lock()

    def __call__(self, topic: str, data: bytes, retained: bool) -> None:
        now = time.monotonic()
        try:
            parsed = json.loads(data)
        except ValueError:
            parsed = None
        message = parsed if isinstance(parsed, dict) else None
        with self._lock:
            # Before the case starts (start unset) everything is at -1: it never counts.
            t_ms = (now - self.start) * 1000 if self.start is not None else -1.0
            self.items.append(Observed(t_ms, topic, retained, message))


def _execute(step: Step, session: Session, injector: BusService, config: dict) -> None:
    if step.publish:
        injector.publish_raw(step.publish.topic, envelope_for(step.publish.topic,
                                                              step.publish.payload))  # fmt: skip
    elif step.publish_raw:
        injector.publish_raw(step.publish_raw.topic, step.publish_raw.text.encode())
    elif step.stop:
        session.stop(COMPONENTS[step.stop.component], abrupt=step.stop.mode == "abrupt")
    elif step.start:
        if step.start.component == "brain":
            session.start_brain(config, wait=False)
        else:
            session.start_sim_body(*SIM_BODY_ARGS, wait=False)


def _check_components(case: Case) -> None:
    for step in case.when:
        action = step.stop or step.start
        if action and action.component not in COMPONENTS:
            known = ", ".join(COMPONENTS)
            raise ValueError(f"unknown component {action.component!r} (known: {known})")


def run_case(case: Case, file: Path, work_dir: Path) -> CaseResult:
    started = time.monotonic()
    name = str(file.relative_to(ROOT)) if file.is_relative_to(ROOT) else str(file)
    try:
        config = BrainConfig.model_validate(case.given.config).model_dump(
            exclude_unset=True
        )  # only what the case sets; the brain keeps its defaults for the rest
        _check_components(case)
        observer = _Observer()
        with Session(work_dir / case.id) as session:
            session.start_brain(config)
            session.start_sim_body(*SIM_BODY_ARGS)
            with session.broker.service("eval") as injector:
                injector.subscribe_raw("sancho/#", observer)
                t0 = time.monotonic()
                observer.start = t0
                for step in case.when:
                    delay = t0 + step.at_ms / 1000 - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                    _execute(step, session, injector, config)
                remaining = t0 + duration_ms(case) / 1000 - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
        checks = verify(case, observer.items)
        result = "pass" if all(c.ok for c in checks) else "fail"
        return CaseResult(case.id, name, result, _ms_since(started), checks)
    except ValidationError as error:
        return CaseResult(case.id, name, "error", _ms_since(started),
                          error=f"given.config: {error}")  # fmt: skip
    except Exception as error:
        detail = "".join(traceback.format_exception_only(error)).strip()
        return CaseResult(case.id, name, "error", _ms_since(started), error=detail)


def _ms_since(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 1)


# --- results ----------------------------------------------------------------------


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def report(results: list[CaseResult], started_at: datetime) -> dict:
    status = _git("status", "--porcelain")
    return {
        "date": format_timestamp(started_at),
        "commit": _git("rev-parse", "--short", "HEAD") or "unknown",
        "dirty": bool(status) if status is not None else None,
        "machine": f"{platform.system()} {platform.machine()}",
        "python": platform.python_version(),
        "cases_version": CASES_VERSION,
        "summary": {
            kind: sum(r.result == kind for r in results) for kind in ("pass", "fail", "error")
        },
        "cases": [asdict(r) for r in results],
    }


def save(data: dict, results_dir: Path) -> Path:
    stamp = data["date"].replace(":", "").replace("-", "").split(".")[0] + "Z"
    path = results_dir / f"{stamp}-{data['commit']}.json"
    results_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def summary(results: list[CaseResult]) -> str:
    lines = ["Banco de evaluación"]
    for r in results:
        mark = {"pass": "PASA ", "fail": "FALLA", "error": "ERROR"}[r.result]
        lines.append(f"  {mark} {r.id}  ({r.duration_ms / 1000:.1f} s)")
        for c in r.checks:
            if not c.ok:
                rule = "al menos" if c.kind == "expect" else "como máximo"
                lines.append(f"        {c.kind} {c.topic}: {c.observed} en {c.within_ms} ms, "
                             f"se esperaba {rule} {c.limit}")  # fmt: skip
        if r.error:
            lines.append(f"        {r.error}")
    passed = sum(r.result == "pass" for r in results)
    lines.append(f"  {passed}/{len(results)} casos pasan")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval", description=__doc__.split("\n")[0])
    parser.add_argument("--cases", type=Path, default=CASES_DIR)
    parser.add_argument("--only", action="append", help="run only this case id (repeatable)")
    parser.add_argument("--results", type=Path, default=RESULTS_DIR)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args(argv)
    if not broker_available():
        print(f"make bench necesita el broker: ejecuta `{PULL_HINT}` o define MOSQUITTO",
              file=sys.stderr)  # fmt: skip
        return 2
    files = sorted(args.cases.glob("*.yaml"))
    cases = [(load_case(f), f) for f in files]  # an invalid case stops the bench here
    if args.only:
        cases = [(c, f) for c, f in cases if c.id in args.only]
    started_at = utc_now()
    work_dir = WORK_DIR / started_at.strftime("%Y%m%dT%H%M%SZ")
    results = []
    for case, file in cases:
        print(f"  … {case.id}", flush=True)
        results.append(run_case(case, file, work_dir))
    print(summary(results))
    if not args.no_save:
        path = save(report(results, started_at), args.results)
        print(f"  resultados: {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    print(f"  logs y grabaciones: {work_dir}")
    return 0 if results and all(r.result == "pass" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
