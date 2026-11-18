"""Publishes a recording again, keeping its relative times (T9, grabaciones.md).

    python -m sim.replay --password-file credentials/replay --recording FILE [--port 1883]

Uses the `replay` role, which only exists in the test broker. Publishes only events
(`sancho/body/+/evt/#`) that were not retained, shifting every `ts` by the same offset
and setting `source` to `replay`; ids, trace ids and payloads stay as recorded, and raw
lines go out exactly as they were. Nothing is validated: invalid messages are replayed.
"""

import argparse
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import paho.mqtt.client as mqtt

from contracts.recordings import RecordLine, read_recording
from contracts.runtime import add_bus_arguments, read_password, setup_logging, stop_on_signals
from contracts.service import BusService
from contracts.types import format_timestamp, parse_timestamp, utc_now

REPLAYED = "sancho/body/+/evt/#"
log = logging.getLogger("sancho.replay")


@dataclass(frozen=True)
class Item:
    t_ms: int
    topic: str
    line: RecordLine


def _ts(line: RecordLine) -> datetime | None:
    if line.message is None:
        return None
    try:
        return parse_timestamp(line.message.get("ts"))
    except ValueError:
        return None


def selected(lines: list[RecordLine]) -> list[Item]:
    """What gets replayed: recorded events that were not retained."""
    return [
        Item(line.t_ms, line.topic, line)
        for line in lines
        if not line.retained and mqtt.topic_matches_sub(REPLAYED, line.topic)
    ]


def rewrite(line: RecordLine, offset: timedelta) -> bytes:
    """Shifts `ts` and sets `source`; leaves everything else, and raw text, untouched."""
    if line.message is None:
        return line.data()
    message = dict(line.message)
    ts = _ts(line)
    if ts is not None:
        message["ts"] = format_timestamp(ts + offset)
    message["source"] = "replay"
    return json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode()


def play(service: BusService, lines: list[RecordLine], stop: threading.Event) -> int:
    items = selected(lines)
    if not items:
        return 0
    started_at, started = utc_now(), time.monotonic()
    first_ts = next((ts for ts in map(_ts, (i.line for i in items)) if ts is not None), None)
    offset = (started_at - first_ts) if first_ts is not None else timedelta(0)
    first_t = items[0].t_ms
    for item in items:
        delay = started + (item.t_ms - first_t) / 1000 - time.monotonic()
        if (delay > 0 and stop.wait(delay)) or stop.is_set():
            break
        service.publish_raw(item.topic, rewrite(item.line, offset))
    return len(items)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m sim.replay",
                                     description=__doc__.split("\n")[0])  # fmt: skip
    add_bus_arguments(parser, traces=False)
    parser.add_argument("--recording", type=Path, required=True)
    args = parser.parse_args(argv)
    setup_logging()
    lines = read_recording(args.recording)
    stop = stop_on_signals()
    with BusService("replay", read_password(args.password_file), host=args.host,
                    port=args.port) as service:  # fmt: skip
        count = play(service, lines, stop)
    log.info("replayed %d messages from %s", count, args.recording)


if __name__ == "__main__":
    main()
