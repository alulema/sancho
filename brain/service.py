"""Minimal orchestrator (T7): `person_entered` in, a greeting out, a trace per decision.

python -m brain --password-file credentials/brain [--port 1883] [--traces traces]
    [--greeting-window-min 10]
"""

import argparse
import logging
import threading
import time
import uuid
from datetime import datetime

from brain.greeter import RULE, BrainConfig, Decision, Greeter
from contracts.bus import Message
from contracts.runtime import (
    add_bus_arguments,
    read_password,
    setup_logging,
    stop_on_signals,
)
from contracts.service import BusError, BusService, Inbox
from contracts.traces import TRACE_VERSION, MessageRefs, TraceRecord, TraceWriter
from contracts.types import utc_now

VERSION = "0.1.0"
ENTERED = "sancho/body/vision/evt/person_entered"
log = logging.getLogger("sancho.brain")


class Brain:
    """Decides on each entry. `service` only needs `publish(message)`."""

    def __init__(self, service, greeter: Greeter, traces: TraceWriter):
        self.service = service
        self.greeter = greeter
        self.traces = traces

    def handle(self, entered: Message, received_at: datetime) -> Decision:
        started = time.perf_counter()
        decision = self.greeter.decide(entered)
        outputs: list[uuid.UUID] = []
        error = None
        if decision.say is not None:
            try:
                self.service.publish(decision.say)
                self.greeter.commit(decision)
                outputs.append(decision.say.envelope.id)
                log.info("greeting %s: %s", entered.payload.track_id, decision.reason)
            except BusError as exc:
                error = str(exc)
                log.error("could not publish the greeting: %s", exc)
        else:
            log.info("not greeting %s: %s", entered.payload.track_id, decision.reason)
        span = uuid.uuid4()
        self._trace(
            entered,
            received_at,
            started,
            span_id=span,
            kind="decision",
            decision=decision.decision,
            reason=decision.reason,
            alternatives=decision.alternatives,
            outputs=outputs,
        )
        if error:
            self._trace(
                entered,
                utc_now(),
                time.perf_counter(),
                parent_span_id=span,
                kind="error",
                reason=error,
            )
        return decision

    def _trace(self, entered, ts, started, *, outputs=(), **fields) -> None:
        self.traces.write(
            TraceRecord(
                v=TRACE_VERSION,
                ts=ts,
                trace_id=entered.envelope.trace_id,
                span_id=fields.pop("span_id", uuid.uuid4()),
                component="brain",
                name=RULE,
                level="L0",
                inputs=MessageRefs(message_ids=[entered.envelope.id]),
                outputs=MessageRefs(message_ids=list(outputs)),
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                **fields,
            )
        )


def run(service: BusService, brain: Brain, stop: threading.Event) -> None:
    inbox = Inbox()
    service.subscribe(ENTERED, inbox.put)
    while not stop.is_set():
        item = inbox.get(timeout_s=0.2)
        if item is not None:
            brain.handle(*item)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m brain", description=__doc__.split("\n")[0])
    add_bus_arguments(parser)
    defaults = BrainConfig()
    parser.add_argument("--greeting-window-min", type=float, default=defaults.greeting_window_min)
    parser.add_argument("--greeting-text", default=defaults.greeting_text)
    parser.add_argument("--lang", default=defaults.lang)
    args = parser.parse_args(argv)
    setup_logging()
    config = BrainConfig(
        greeting_window_min=args.greeting_window_min,
        greeting_text=args.greeting_text,
        lang=args.lang,
    )
    stop = stop_on_signals()
    service = BusService(
        "brain", read_password(args.password_file), host=args.host, port=args.port,
        version=VERSION,
    )  # fmt: skip
    brain = Brain(service, Greeter(config), TraceWriter(args.traces, "brain"))
    with service:
        log.info("brain %s online, window %g min", VERSION, config.greeting_window_min)
        run(service, brain, stop)
    log.info("brain stopped")
