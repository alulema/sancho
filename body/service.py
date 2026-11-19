"""Body agent (T6): camera → person detection → presence events; `say` → local voice.

    python -m body --password-file ~/sancho/broker/credentials/body
        [--models ~/sancho/models] [--sink PULSE_SINK] [--threshold 0.35]
        [--enter-ms 500] [--leave-ms 3000] [--fps 10] [--threads 2]

Runs on the Nano with the `body` role. The vision loop runs on its own thread and
publishes `person_entered` / `person_left`; the main thread speaks `say` commands one
at a time. No image or audio is ever written to disk or published.
"""

import argparse
import logging
import os
import threading
import time
from pathlib import Path

from body.presence import Detection, Entered, Left, Presence
from contracts.bus import make_message
from contracts.runtime import add_bus_arguments, read_password, setup_logging, stop_on_signals
from contracts.service import BusError, BusService, Inbox
from contracts.topics import PersonEntered, PersonLeft
from contracts.traces import TraceWriter
from contracts.types import utc_now

VERSION = "0.1.0"
ENTERED = "sancho/body/vision/evt/person_entered"
LEFT = "sancho/body/vision/evt/person_left"
SAY = "sancho/body/speech/cmd/say"
DETECTOR_MODEL = "nanodet-plus-416.onnx"
VOICE_MODEL = "es_ES-davefx-medium.onnx"
REPORT_EVERY_S = 60.0
log = logging.getLogger("sancho.body")


def presence_message(event: Entered | Left, source: str = "body"):
    if isinstance(event, Entered):
        d = event.detection
        payload = PersonEntered(
            track_id=event.track_id,
            confidence=round(d.score, 3),
            bbox=[round(v, 4) for v in d.bbox],
            first_seen_ts=event.first_seen_ts,
            frame_ts=event.frame_ts,
        )
        return make_message(ENTERED, source, payload)
    return make_message(LEFT, source, PersonLeft(track_id=event.track_id,
                                                 duration_s=event.duration_s))  # fmt: skip


class Vision:
    """Newest frame → detector → presence → bus, until `stop`.

    While `paused()` is true (the body is speaking) it does not detect: on two cores in
    5 W mode, detection makes synthesis slower than real time and the voice stutters
    (T6 log). The paused time does not count as absence.
    """

    def __init__(self, service, camera, detector, presence: Presence,
                 paused=lambda: False):  # fmt: skip
        self.service, self.camera, self.detector, self.presence = (
            service, camera, detector, presence)  # fmt: skip
        self._paused = paused
        self.frames = 0
        self.paused_s = 0.0
        self._busy_s = 0.0

    def _wait_while_paused(self, stop: threading.Event) -> None:
        if not self._paused():
            return
        started = time.monotonic()
        while self._paused() and not stop.wait(0.02):
            pass
        waited = time.monotonic() - started
        self.paused_s += waited
        self.presence.pause(waited)

    def run(self, stop: threading.Event) -> None:
        seq, report_at, reported = 0, time.monotonic() + REPORT_EVERY_S, (0, 0.0)
        while not stop.is_set():
            self._wait_while_paused(stop)
            frame = self.camera.next_frame(seq, timeout_s=2.0)
            if frame is None:
                if not stop.is_set():
                    log.warning("no camera frame in 2 s")
                self._emit(self.presence.update(time.monotonic(), utc_now(), []))
                continue
            seq = frame.seq
            started = time.perf_counter()
            people = [Detection(score, (x, y, w, h))
                      for score, x, y, w, h in self.detector.detect(frame.data)]  # fmt: skip
            self._busy_s += time.perf_counter() - started
            self.frames += 1
            self._emit(self.presence.update(frame.t, frame.ts, people))
            if time.monotonic() >= report_at:
                n, busy = self.frames - reported[0], self._busy_s - reported[1]
                log.info("vision: %.1f frames/s, detector %.0f ms/frame",
                         n / REPORT_EVERY_S, busy / max(n, 1) * 1000)  # fmt: skip
                reported, report_at = (self.frames, self._busy_s), report_at + REPORT_EVERY_S
        self._emit(self.presence.close())

    def _emit(self, event: Entered | Left | None) -> None:
        if event is None:
            return
        try:
            self.service.publish(presence_message(event))
        except BusError as error:  # the bus reconnects; this event is lost and logged
            log.error("could not publish %s: %s", type(event).__name__, error)
            return
        if isinstance(event, Entered):
            log.info("person entered: %s (score %.2f)", event.track_id, event.detection.score)
        else:
            log.info("person left: %s after %.1f s", event.track_id, event.duration_s)


def run(service: BusService, speaker, vision: Vision, stop: threading.Event) -> None:
    inbox = Inbox()
    service.subscribe(SAY, inbox.put)
    thread = threading.Thread(target=vision.run, args=(stop,), name="vision", daemon=True)
    thread.start()
    try:
        while not stop.is_set():
            item = inbox.get(timeout_s=0.1)
            if item is not None:
                speaker.speak(*item)
    finally:
        stop.set()
        thread.join(timeout=10)


def main(argv: list[str] | None = None) -> None:
    from body.camera import Camera, gst_command
    from body.detector import PersonDetector
    from body.speech import Speaker, TtsWorker, paplay_command, worker_command

    parser = argparse.ArgumentParser(prog="python -m body", description=__doc__.split("\n")[0])
    add_bus_arguments(parser)
    parser.add_argument("--models", type=Path, default=Path.home() / "sancho" / "models")
    parser.add_argument("--sink", default=os.environ.get("SANCHO_SINK"),
                        help="PulseAudio sink for the speaker (default: the system's)")  # fmt: skip
    parser.add_argument("--threshold", type=float, default=0.35)
    parser.add_argument("--enter-ms", type=int, default=500)
    parser.add_argument("--leave-ms", type=int, default=3000)
    parser.add_argument("--fps", type=int, default=10, help="camera frames delivered per second")
    parser.add_argument("--threads", type=int, default=2, help="detector threads")
    args = parser.parse_args(argv)
    setup_logging()
    stop = stop_on_signals()
    detector = PersonDetector(str(args.models / DETECTOR_MODEL), threshold=args.threshold,
                              threads=args.threads)  # fmt: skip
    worker = TtsWorker(worker_command(str(args.models / VOICE_MODEL)),
                       cwd=str(Path(__file__).resolve().parent.parent))  # fmt: skip
    worker.start()  # load the voice before going online: the first greeting is not slower
    service = BusService("body", read_password(args.password_file), host=args.host,
                         port=args.port, version=VERSION)  # fmt: skip
    speaker = Speaker(service, TraceWriter(args.traces, "body"), worker,
                      paplay_command(args.sink))  # fmt: skip
    presence = Presence(enter_ms=args.enter_ms, leave_ms=args.leave_ms)
    try:
        with service, Camera(lambda fd: gst_command(fd, fps=args.fps)) as camera:
            log.info("body %s online (sink %s)", VERSION, args.sink or "default")
            vision = Vision(service, camera, detector, presence, paused=speaker.busy.is_set)
            run(service, speaker, vision, stop)
    finally:
        worker.close()
    log.info("body stopped")
