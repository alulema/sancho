"""Records everything that crosses the bus to JSONL (T9, docs/contratos/grabaciones.md).

    python -m sim.recorder --password-file ~/sancho/broker/credentials/recorder
        [--port 1883] [--out recordings] [--duration-s N]

Uses the `recorder` role, which exists in production too: it only reads. Writes
`<out>/<UTC time>.jsonl` and flushes each line, until SIGINT/SIGTERM or the duration.
Stores what it receives without validating: invalid messages are part of a session.
"""

import argparse
import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from contracts.recordings import record
from contracts.runtime import add_bus_arguments, read_password, setup_logging, stop_on_signals
from contracts.service import BusService

log = logging.getLogger("sancho.recorder")


class Recorder:
    """A raw handler (`BusService.subscribe_raw`) that appends each message to `path`."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", encoding="utf-8")
        self._start = time.monotonic()
        self._lock = threading.Lock()
        self.count = 0

    def __call__(self, topic: str, data: bytes, retained: bool) -> None:
        t_ms = int((time.monotonic() - self._start) * 1000)
        line = record(t_ms, topic, data, retained).to_jsonl()
        with self._lock:
            self._file.write(line)
            self._file.flush()
            self.count += 1

    def close(self) -> None:
        with self._lock:
            self._file.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m sim.recorder",
                                     description=__doc__.split("\n")[0])  # fmt: skip
    add_bus_arguments(parser, traces=False)
    parser.add_argument("--out", type=Path, default=Path("recordings"))
    parser.add_argument("--duration-s", type=float)
    args = parser.parse_args(argv)
    setup_logging()
    stop = stop_on_signals()
    path = args.out / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".jsonl")
    recorder = Recorder(path)
    service = BusService("recorder", read_password(args.password_file), host=args.host,
                         port=args.port)  # fmt: skip
    with service:
        service.subscribe_raw("sancho/#", recorder)
        log.info("recording to %s", path)
        stop.wait(args.duration_s)
    recorder.close()
    log.info("recorded %d messages in %s", recorder.count, path)


if __name__ == "__main__":
    main()
