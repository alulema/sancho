"""Checks a running broker against the T4 acceptance criteria.

Runs where the credentials are (the Nano in production) and touches only the bus:
    python -m deploy.broker.smoke_check --credentials ~/sancho/broker/credentials

Exits with 1 if any check fails. Uses the production roles (body, brain, recorder).
"""

import argparse
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from contracts.bus import decode, encode, make_message
from contracts.service import BusService, PublishDenied
from contracts.topics import PersonEntered, Say, health_topic

ENTERED = "sancho/body/vision/evt/person_entered"
SAY = "sancho/body/speech/cmd/say"
SERVICE = (
    "import sys, time\n"
    "from contracts.service import BusService\n"
    "BusService(sys.argv[1], sys.argv[2], host=sys.argv[3], port=int(sys.argv[4])).connect()\n"
    "print('ready', flush=True)\n"
    "time.sleep(60)\n"
)


def raw_connect(host, port, username=None, password=None):
    """Returns the CONNACK reason of a bare MQTT v5 connection."""
    done = threading.Event()
    result = {}
    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id=f"smoke-{uuid.uuid4().hex[:8]}",
        protocol=mqtt.MQTTv5,
    )
    if username:
        client.username_pw_set(username, password)

    def on_connect(c, u, flags, reason, properties):
        result["reason"] = reason
        done.set()

    client.on_connect = on_connect
    client.connect(host, port)
    client.loop_start()
    done.wait(5)
    client.disconnect()
    client.loop_stop()
    return result.get("reason")


class Recorder:
    def __init__(self, service: BusService):
        self.messages = []
        service.subscribe("sancho/#", self.messages.append)

    def wait(self, predicate, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for m in list(self.messages):
                if predicate(m):
                    return m
            time.sleep(0.02)
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    args = parser.parse_args()
    password = {p.name: p.read_text().strip() for p in args.credentials.iterdir()}
    host, port = args.host, args.port
    results = []

    def check(name, ok):
        results.append(ok)
        print(f"{'OK  ' if ok else 'FAIL'} {name}")

    reason = raw_connect(host, port)
    check("client without credentials is rejected", reason is not None and reason.is_failure)
    reason = raw_connect(host, port, "body", "wrong")
    check("wrong password is rejected", reason is not None and reason.is_failure)
    reason = raw_connect(host, port, "eval", "any")
    check("test-only role 'eval' does not exist", reason is not None and reason.is_failure)

    with BusService("recorder", password["recorder"], host=host, port=port) as recorder_service:
        recorder = Recorder(recorder_service)
        with BusService("body", password["body"], host=host, port=port) as body:
            event = make_message(
                ENTERED, "body", PersonEntered(track_id="smoke", confidence=1, bbox=[0, 0, 1, 1])
            )
            body.publish(event)
            seen = recorder.wait(lambda m: m.envelope.id == event.envelope.id)
            check("body publishes its event and recorder receives it", seen is not None)

            say = make_message(
                SAY, "brain", Say(say_id=uuid.uuid4(), text="x", lang="es", priority="normal")
            )
            refused = raw_publish(host, port, "body", password["body"], SAY, encode(say))
            time.sleep(0.5)
            leaked = any(m.envelope.id == say.envelope.id for m in recorder.messages)
            check("body cannot publish a command (0x87, not delivered)", refused and not leaked)
            try:
                body.publish(say)
                check("BusService refuses a foreign topic before sending", False)
            except PublishDenied:
                check("BusService refuses a foreign topic before sending", True)

        process = subprocess.Popen(
            [sys.executable, "-c", SERVICE, "brain", password["brain"], host, str(port)],
            cwd=Path(__file__).resolve().parents[2],
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            ready = process.stdout.readline().strip() == "ready"
            topic = health_topic("brain")
            online = recorder.wait(lambda m: m.topic == topic and m.payload.status == "online")
            killed_at = time.monotonic()
            process.send_signal(signal.SIGKILL)
            will = recorder.wait(lambda m: m.topic == topic and m.payload.last_will is True)
            delay = time.monotonic() - killed_at
        finally:
            process.kill()
            process.wait()
        check("brain announces online", ready and online is not None)
        ok = will is not None and decode(topic, encode(will)).payload.status == "offline"
        check(f"killed brain leaves its last will ({delay:.2f} s)", ok)

    print(f"{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


def raw_publish(host, port, username, password, topic, payload) -> bool:
    """True if the broker refuses the publish as not authorized."""
    acks = {}
    done = threading.Event()
    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id=f"smoke-{uuid.uuid4().hex[:8]}",
        protocol=mqtt.MQTTv5,
    )
    client.username_pw_set(username, password)
    client.on_connect = lambda c, u, f, r, p: done.set()
    client.on_publish = lambda c, u, mid, reason, p: acks.__setitem__(mid, reason)
    client.connect(host, port)
    client.loop_start()
    done.wait(5)
    info = client.publish(topic, payload, qos=1)
    info.wait_for_publish(5)
    deadline = time.monotonic() + 5
    while info.mid not in acks and time.monotonic() < deadline:
        time.sleep(0.01)
    client.disconnect()
    client.loop_stop()
    reason = acks.get(info.mid)
    return reason is not None and reason.value == 0x87


if __name__ == "__main__":
    sys.exit(main())
