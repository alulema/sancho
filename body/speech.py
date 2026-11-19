"""Local speech (T6, ADR-0018): `say` commands to the speaker, with `speech/status`.

The Piper voice lives in a worker process (body/tts_worker.py, GPL-3.0) that is
loaded once and reused; audio flows from its stdout to `paplay` through memory and
never touches the disk. `started` is published when the first audio chunk goes to
the player (synthesis is done sentence by sentence) and `finished` when the player
has played everything.
"""

import json
import logging
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import datetime

from body.ttsproto import AUDIO, END, ERROR, READY, ProtocolError, read_frame, request
from contracts.bus import Message, make_message
from contracts.topics import SpeechStatus
from contracts.traces import TRACE_VERSION, MessageRefs, TraceRecord, TraceWriter

STATUS = "sancho/body/speech/evt/status"
log = logging.getLogger("sancho.body.speech")


class TtsError(Exception):
    pass


def worker_command(model: str) -> list[str]:
    return [sys.executable, "-m", "body.tts_worker", "--model", model]


def paplay_command(sink: str | None, *, latency_ms: int = 200) -> Callable[[int], list[str]]:
    """paplay's default buffer is about 2 s: `finished` came that late and the sound
    started well after `started`. 200 ms plays without cuts on the Nano (T6 log)."""

    def command(sample_rate: int) -> list[str]:
        args = ["paplay", "--raw", f"--rate={sample_rate}", "--channels=1", "--format=s16le",
                f"--latency-msec={latency_ms}"]  # fmt: skip
        return args + ([f"--device={sink}"] if sink else [])

    return command


class TtsWorker:
    """The worker process; restarted on the next request if it dies."""

    def __init__(self, command: list[str], *, cwd: str | None = None):
        self._command, self._cwd = command, cwd
        self._process: subprocess.Popen | None = None
        self.sample_rate: int | None = None
        self.starts = 0

    def start(self) -> None:
        self.close()
        self.starts += 1
        started = time.perf_counter()
        self._process = subprocess.Popen(self._command, stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, cwd=self._cwd)  # fmt: skip
        frame = self._read()
        if frame is None or frame[0] != READY:
            detail = json.loads(frame[1]).get("error") if frame else "worker exited"
            self.close()
            raise TtsError(f"TTS worker did not start: {detail}")
        self.sample_rate = int(json.loads(frame[1])["sample_rate"])
        log.info("voice loaded in %.1f s (%d Hz)", time.perf_counter() - started,
                 self.sample_rate)  # fmt: skip

    def synthesize(self, text_id: str, text: str) -> Iterator[bytes]:
        """Audio chunks for one text; raises TtsError if synthesis fails."""
        if self._process is None or self._process.poll() is not None:
            self.start()
        try:
            self._process.stdin.write(request(text_id, text))
            self._process.stdin.flush()
        except OSError as error:
            self.close()
            raise TtsError(f"TTS worker is gone: {error}") from error
        while True:
            frame = self._read()
            if frame is None:
                self.close()
                raise TtsError("TTS worker exited while synthesizing")
            kind, data = frame
            if kind == AUDIO:
                yield data
            elif kind == END:
                return
            elif kind == ERROR:
                raise TtsError(json.loads(data).get("error") or "synthesis failed")

    def _read(self):
        try:
            return read_frame(self._process.stdout)
        except ProtocolError as error:
            log.error("TTS worker protocol: %s", error)
            return None

    def close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        if process.stdin:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


class Speaker:
    """Takes `say` commands one at a time and publishes their status."""

    def __init__(self, service, traces: TraceWriter, worker: TtsWorker,
                 player: Callable[[int], list[str]], *, component: str = "body"):  # fmt: skip
        self.service, self.traces, self.worker = service, traces, worker
        self._player, self._component = player, component
        self.busy = threading.Event()

    def speak(self, say: Message, received_at: datetime) -> str:
        """Returns the final state: finished or error."""
        self.busy.set()
        started = time.perf_counter()
        statuses: list[Message] = []
        error: str | None = None
        try:
            log.info("saying (%s): %s", say.payload.lang, say.payload.text)
            self._play(say, statuses)
        except (TtsError, OSError) as failure:
            error = str(failure) or failure.__class__.__name__
            log.error("could not say %s: %s", say.payload.say_id, error)
            statuses.append(self._status(say, "error", error))
        finally:
            self.busy.clear()
        self.traces.write(TraceRecord(
            v=TRACE_VERSION, ts=received_at, trace_id=say.envelope.trace_id,
            span_id=uuid.uuid4(), component=self._component,
            kind="error" if error else "action", name="speak", level="L0",
            inputs=MessageRefs(message_ids=[say.envelope.id]),
            outputs=MessageRefs(message_ids=[s.envelope.id for s in statuses]),
            reason=error, duration_ms=round((time.perf_counter() - started) * 1000, 3),
        ))  # fmt: skip
        return "error" if error else "finished"

    def _play(self, say: Message, statuses: list[Message]) -> None:
        chunks = self.worker.synthesize(str(say.payload.say_id), say.payload.text)
        player = None
        try:
            for chunk in chunks:
                if player is None:
                    player = subprocess.Popen(self._player(self.worker.sample_rate),
                                              stdin=subprocess.PIPE)  # fmt: skip
                    player.stdin.write(chunk)
                    player.stdin.flush()
                    statuses.append(self._status(say, "started"))
                else:
                    player.stdin.write(chunk)
            if player is None:
                raise TtsError("synthesis produced no audio")
            player.stdin.close()
            code = player.wait()
            if code != 0:
                raise TtsError(f"player exited with code {code}")
            statuses.append(self._status(say, "finished"))
        finally:
            if player is not None and player.poll() is None:
                player.kill()
                player.wait()

    def _status(self, say: Message, state: str, error: str | None = None) -> Message:
        status = make_message(
            STATUS, self._component, SpeechStatus(say_id=say.payload.say_id, state=state,
                                                  error=error),
            trace_id=say.envelope.trace_id, causation_id=say.envelope.id,
        )  # fmt: skip
        self.service.publish(status)
        return status
