"""Simulated body (T8): a scripted camera and a TTS that only logs, as role `sim`.

    python -m sim.body --password-file credentials/sim [--port 1883] [--script FILE]
        [--synth-ms 200] [--speech-ms 1000] [--exit-after-script] [--linger-ms 2000]

It speaks the body's contract (topicos-e0.md) and uses `sancho/sys/body/health`, so
the brain cannot tell it from the real body. It never touches audio or images.
"""

import argparse
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from contracts.bus import Message, make_message
from contracts.runtime import add_bus_arguments, read_password, setup_logging, stop_on_signals
from contracts.service import BusService, Inbox
from contracts.topics import PersonEntered, PersonLeft, SpeechStatus
from contracts.traces import TRACE_VERSION, MessageRefs, TraceRecord, TraceWriter
from contracts.types import utc_now
from sim.script import Script, load_script

VERSION = "0.1.0"
ENTERED = "sancho/body/vision/evt/person_entered"
LEFT = "sancho/body/vision/evt/person_left"
SAY = "sancho/body/speech/cmd/say"
STATUS = "sancho/body/speech/evt/status"
log = logging.getLogger("sancho.sim")


class Camera:
    """Plays a script: publishes `person_entered` and `person_left` at their times."""

    def __init__(self, service, script: Script):
        self.service = service
        self.script = script

    def play(self, stop: threading.Event) -> None:
        start = time.monotonic()
        entered_at: dict[str, float] = {}
        for step in self.script.steps:
            delay = start + step.at_ms / 1000 - time.monotonic()
            if (delay > 0 and stop.wait(delay)) or stop.is_set():
                return
            if step.enter:
                entered_at[step.enter.track_id] = time.monotonic()
                self.service.publish(self._entered(step.enter))
                log.info("camera: %s entered", step.enter.track_id)
            else:
                assert step.leave is not None
                track = step.leave.track_id
                duration = round(time.monotonic() - entered_at.pop(track), 3)
                self.service.publish(
                    make_message(LEFT, "sim", PersonLeft(track_id=track, duration_s=duration))
                )
                log.info("camera: %s left after %.1f s", track, duration)

    def _entered(self, enter) -> Message:
        frame_ts = utc_now()
        payload = PersonEntered(
            track_id=enter.track_id,
            confidence=enter.confidence,
            bbox=enter.bbox,
            first_seen_ts=frame_ts - timedelta(milliseconds=enter.hysteresis_ms),
            frame_ts=frame_ts,
        )
        return make_message(ENTERED, "sim", payload)


class Speaker:
    """Takes `say` commands one at a time: logs the text, pretends to synthesize and to
    play it, and publishes `started` and `finished` like the real body would."""

    def __init__(self, service, traces: TraceWriter, *, synth_ms: int, speech_ms: int,
                 sleep=time.sleep):  # fmt: skip
        self.service = service
        self.traces = traces
        self.synth_ms, self.speech_ms = synth_ms, speech_ms
        self._sleep = sleep
        self.busy = threading.Event()

    def speak(self, say: Message, received_at: datetime) -> None:
        self.busy.set()
        try:
            started = time.perf_counter()
            log.info("speaker says (%s): %s", say.payload.lang, say.payload.text)
            self._sleep(self.synth_ms / 1000)
            statuses = [self._status(say, "started")]
            self._sleep(self.speech_ms / 1000)
            statuses.append(self._status(say, "finished"))
            self.traces.write(
                TraceRecord(
                    v=TRACE_VERSION,
                    ts=received_at,
                    trace_id=say.envelope.trace_id,
                    span_id=uuid.uuid4(),
                    component="sim",
                    kind="action",
                    name="speak",
                    level="L0",
                    inputs=MessageRefs(message_ids=[say.envelope.id]),
                    outputs=MessageRefs(message_ids=[s.envelope.id for s in statuses]),
                    duration_ms=round((time.perf_counter() - started) * 1000, 3),
                )
            )
        finally:
            self.busy.clear()

    def _status(self, say: Message, state: str) -> Message:
        status = make_message(
            STATUS,
            "sim",
            SpeechStatus(say_id=say.payload.say_id, state=state),
            trace_id=say.envelope.trace_id,
            causation_id=say.envelope.id,
        )
        self.service.publish(status)
        return status


def run(service: BusService, speaker: Speaker, camera: Camera | None, stop: threading.Event,
        *, exit_after_script: bool = False, linger_ms: int = 2000) -> None:  # fmt: skip
    inbox = Inbox()
    service.subscribe(SAY, inbox.put)
    played = threading.Event()
    if camera:

        def play():
            try:
                camera.play(stop)
            finally:
                played.set()

        threading.Thread(target=play, name="camera", daemon=True).start()
    idle_since = None
    while not stop.is_set():
        item = inbox.get(timeout_s=0.05)
        if item is not None:
            speaker.speak(*item)
            idle_since = None
            continue
        if exit_after_script and camera and played.is_set():
            idle_since = idle_since or time.monotonic()
            if time.monotonic() - idle_since >= linger_ms / 1000:
                log.info("script done and speaker idle for %d ms; exiting", linger_ms)
                return


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m sim.body", description=__doc__.split("\n")[0])
    add_bus_arguments(parser)
    parser.add_argument("--script", type=Path, help="camera script (sim/scripts/*.yaml)")
    parser.add_argument("--synth-ms", type=int, default=200, help="before 'started'")
    parser.add_argument("--speech-ms", type=int, default=1000, help="from 'started' to 'finished'")
    parser.add_argument("--exit-after-script", action="store_true")
    parser.add_argument("--linger-ms", type=int, default=2000,
                        help="with --exit-after-script: idle time before exiting")  # fmt: skip
    args = parser.parse_args(argv)
    setup_logging()
    script = load_script(args.script) if args.script else None
    stop = stop_on_signals()
    service = BusService(
        "sim", read_password(args.password_file), host=args.host, port=args.port,
        version=VERSION,
    )  # fmt: skip
    speaker = Speaker(
        service, TraceWriter(args.traces, "sim"), synth_ms=args.synth_ms,
        speech_ms=args.speech_ms,
    )  # fmt: skip
    with service:
        camera = Camera(service, script) if script else None
        log.info("sim body %s online%s", VERSION, f", script {args.script}" if script else "")
        run(service, speaker, camera, stop, exit_after_script=args.exit_after_script,
            linger_ms=args.linger_ms)  # fmt: skip
    log.info("sim body stopped")


if __name__ == "__main__":
    main()
