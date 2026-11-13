"""T4 acceptance against a real Mosquitto broker started with the generated config.

By default the broker runs in the same pinned image as on the Nano, so Docker and
that image are needed (the tests never pull it). MOSQUITTO=/path/to/mosquitto runs a
native binary instead (Ubuntu's AppArmor profile stops /usr/sbin/mosquitto from
reading a config outside /etc/mosquitto). Without either, the tests are skipped.
"""

import os
import shutil
import signal
import socket
import subprocess
import sys
import textwrap
import threading
import time
import uuid
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.enums import CallbackAPIVersion

from contracts.acl import ROLES, roles_for
from contracts.bus import decode, encode, make_message
from contracts.service import BusError, BusService, PublishDenied
from contracts.topics import PersonEntered, Say, health_topic
from deploy.broker.broker_config import BROKER_DIR_IN_IMAGE, MOSQUITTO_IMAGE, generate

MOSQUITTO = os.environ.get("MOSQUITTO")


def _image_available() -> bool:
    """Never pulls: tests must not download anything by themselves."""
    if not shutil.which("docker"):
        return False
    inspect = ["docker", "image", "inspect", MOSQUITTO_IMAGE]
    return subprocess.run(inspect, capture_output=True).returncode == 0


pytestmark = pytest.mark.skipif(
    not MOSQUITTO and not _image_available(),
    reason=f"no broker: run `docker pull {MOSQUITTO_IMAGE}` or set MOSQUITTO",
)

ROOT = Path(__file__).resolve().parent.parent
ENTERED = "sancho/body/vision/evt/person_entered"
SAY = "sancho/body/speech/cmd/say"
DELIVERY_WAIT_S = 0.5


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Broker:
    def __init__(self, directory: Path, environment: str):
        self.port = free_port()
        self.container = None
        listeners = [f"127.0.0.1:{self.port}"]
        if MOSQUITTO:
            self.passwords = generate(directory, environment, listeners)
            command = [MOSQUITTO, "-c", str(directory / "mosquitto.conf")]
        else:
            self.passwords = generate(
                directory, environment, listeners, broker_dir=BROKER_DIR_IN_IMAGE
            )
            self.container = f"sancho-test-broker-{uuid.uuid4().hex[:8]}"
            command = [
                "docker", "run", "--rm", "--name", self.container, "--network", "host",
                "--user", f"{os.getuid()}:{os.getgid()}",
                "-v", f"{directory}:{BROKER_DIR_IN_IMAGE}:ro",
                MOSQUITTO_IMAGE, "mosquitto", "-c", f"{BROKER_DIR_IN_IMAGE}/mosquitto.conf",
            ]  # fmt: skip
        self.log = directory.parent / f"{directory.name}-broker.log"
        with self.log.open("w") as log:
            self.process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"mosquitto exited:\n{self.log.read_text()}")
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("mosquitto did not start")

    def service(self, role: str, **kwargs) -> BusService:
        return BusService(role, self.passwords[role], port=self.port, **kwargs)

    def stop(self) -> None:
        if self.container:
            subprocess.run(["docker", "rm", "-f", self.container], capture_output=True)
        self.process.terminate()
        self.process.wait(5)


@pytest.fixture(scope="module")
def broker(tmp_path_factory):
    b = Broker(tmp_path_factory.mktemp("broker-test"), "test")
    yield b
    b.stop()


class RawClient:
    """A bare MQTT v5 client, to test what the broker allows without our checks."""

    def __init__(self, port: int, username: str | None = None, password: str | None = None):
        self.connected = threading.Event()
        self.reason = None
        self.messages: list[mqtt.MQTTMessage] = []
        self.acks: dict[int, object] = {}
        self.client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=f"raw-{uuid.uuid4().hex[:8]}",
            protocol=mqtt.MQTTv5,
        )
        if username:
            self.client.username_pw_set(username, password)
        self.client.on_connect = self._on_connect
        self.client.on_message = lambda c, u, m: self.messages.append(m)
        self.client.on_publish = self._on_ack
        self.client.on_subscribe = self._on_ack
        self.client.connect("127.0.0.1", port)
        self.client.loop_start()
        self.connected.wait(5)

    def _on_connect(self, client, userdata, flags, reason, properties):
        self.reason = reason
        self.connected.set()

    def _on_ack(self, client, userdata, mid, reason, properties):
        self.acks[mid] = reason

    @property
    def accepted(self) -> bool:
        return self.reason is not None and not self.reason.is_failure

    def subscribe(self, pattern: str):
        _, mid = self.client.subscribe(pattern, qos=1)
        return self._ack(mid)

    def publish(self, topic: str, payload: bytes, retain: bool = False):
        info = self.client.publish(topic, payload, qos=1, retain=retain)
        info.wait_for_publish(5)
        return self._ack(info.mid)

    def _ack(self, mid):
        deadline = time.monotonic() + 5
        while mid not in self.acks and time.monotonic() < deadline:
            time.sleep(0.01)
        return self.acks.get(mid)

    def received(self, topic: str) -> list[mqtt.MQTTMessage]:
        return [m for m in self.messages if m.topic == topic]

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()


@pytest.fixture
def raw(broker):
    clients = []

    def connect(username=None, password=None):
        client = RawClient(broker.port, username, password)
        clients.append(client)
        return client

    yield connect
    for client in clients:
        client.close()


@pytest.fixture
def watcher(broker, raw):
    """`eval` subscribed to everything, as the bench will be."""
    client = raw("eval", broker.passwords["eval"])
    assert client.accepted
    assert not client.subscribe("sancho/#")[0].is_failure
    return client


def entered_message(source="body"):
    payload = PersonEntered(track_id="t1", confidence=0.9, bbox=[0.4, 0.3, 0.2, 0.3])
    return make_message(ENTERED, source, payload)


def say_message():
    return make_message(
        SAY, "brain", Say(say_id=uuid.uuid4(), text="Hola", lang="es", priority="normal")
    )


# --- authentication -----------------------------------------------------------------


def test_client_without_credentials_is_rejected(raw):
    client = raw()
    assert client.connected.is_set() and not client.accepted


def test_wrong_password_is_rejected(raw):
    assert not raw("body", "not-the-password").accepted


def test_unknown_user_is_rejected(raw):
    assert not raw("intruder", "whatever").accepted


@pytest.mark.parametrize("role", [r.name for r in roles_for("test")])
def test_every_role_can_connect(raw, broker, role):
    assert raw(role, broker.passwords[role]).accepted


# --- authorization ------------------------------------------------------------------

ALLOWED = [
    ("body", ENTERED),
    ("body", health_topic("body")),
    ("brain", SAY),
    ("brain", health_topic("brain")),
    ("sim", ENTERED),
    ("sim", health_topic("body")),
    ("replay", ENTERED),
    ("eval", SAY),
]

FORBIDDEN = [
    ("body", SAY),  # its own commands come from others
    ("body", health_topic("brain")),
    ("brain", ENTERED),
    ("brain", health_topic("body")),
    ("recorder", ENTERED),
    ("recorder", "sancho/sys/recorder/health"),
    ("sim", SAY),
    ("replay", SAY),
    ("replay", health_topic("body")),
]


@pytest.mark.parametrize(("role", "topic"), ALLOWED)
def test_role_can_publish_on_its_topics(broker, raw, watcher, role, topic):
    client = raw(role, broker.passwords[role])
    reason = client.publish(topic, b"probe")
    assert not reason.is_failure
    time.sleep(DELIVERY_WAIT_S)
    assert any(m.payload == b"probe" for m in watcher.received(topic))


@pytest.mark.parametrize(("role", "topic"), FORBIDDEN)
def test_role_cannot_publish_on_foreign_topics(broker, raw, watcher, role, topic):
    client = raw(role, broker.passwords[role])
    marker = f"forbidden-{uuid.uuid4().hex}".encode()
    reason = client.publish(topic, marker)
    assert reason.is_failure and reason.value == 0x87  # Not authorized
    time.sleep(DELIVERY_WAIT_S)
    assert not any(m.payload == marker for m in watcher.messages)


NOT_READABLE = [
    ("body", "sancho/body/+/evt/#", ENTERED),
    ("body", "sancho/#", ENTERED),
    ("brain", "sancho/body/+/cmd/#", SAY),
    ("replay", "sancho/#", ENTERED),
]


@pytest.mark.parametrize(("role", "pattern", "topic"), NOT_READABLE)
def test_role_does_not_receive_outside_its_topics(broker, raw, role, pattern, topic):
    # Mosquitto's acl_file grants any subscription and filters each message on
    # delivery, so the guarantee to test is that nothing arrives.
    client = raw(role, broker.passwords[role])
    client.subscribe(pattern)
    raw("eval", broker.passwords["eval"]).publish(topic, b"secret")
    time.sleep(DELIVERY_WAIT_S)
    assert client.received(topic) == []


def test_component_refuses_to_publish_where_its_role_cannot(broker):
    with broker.service("body") as body, pytest.raises(PublishDenied):
        body.publish(say_message())


def test_oversized_message_is_refused(broker, raw, watcher):
    client = raw("body", broker.passwords["body"])
    client.publish(ENTERED, b"x" * 70_000)
    time.sleep(DELIVERY_WAIT_S)
    assert not any(len(m.payload) >= 70_000 for m in watcher.messages)


# --- services, validation, health and last will -------------------------------------


def test_message_round_trip_between_services(broker):
    received = []
    with broker.service("brain") as brain, broker.service("body") as body:
        brain.subscribe("sancho/body/+/evt/#", received.append)
        sent = entered_message()
        body.publish(sent)
        deadline = time.monotonic() + 2
        while not received and time.monotonic() < deadline:
            time.sleep(0.01)
    assert [m.envelope.id for m in received] == [sent.envelope.id]


def test_invalid_message_is_logged_and_service_keeps_working(broker, raw, caplog):
    received = []
    with broker.service("brain") as brain:
        brain.subscribe("sancho/body/+/evt/#", received.append)
        body = raw("body", broker.passwords["body"])
        body.publish(ENTERED, b"{esto no es JSON")
        body.publish(ENTERED, encode(entered_message()))
        deadline = time.monotonic() + 2
        while not received and time.monotonic() < deadline:
            time.sleep(0.01)
    assert len(received) == 1
    assert any("rejected message" in r.getMessage() for r in caplog.records)


def test_handler_error_does_not_stop_the_service(broker):
    calls = []

    def flaky(message):
        calls.append(message)
        if len(calls) == 1:
            raise RuntimeError("bug in a handler")

    with broker.service("brain") as brain, broker.service("body") as body:
        brain.subscribe("sancho/body/+/evt/#", flaky)
        body.publish(entered_message())
        body.publish(entered_message())
        deadline = time.monotonic() + 2
        while len(calls) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
    assert len(calls) == 2


def wait_for_health(watcher, topic, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for m in watcher.received(topic):
            message = decode(topic, m.payload)
            if predicate(message.payload):
                return message
        time.sleep(0.02)
    raise AssertionError(f"no matching health message on {topic}")


def test_service_announces_online_and_clean_offline(broker, watcher):
    topic = health_topic("brain")
    with broker.service("brain", version="1.2.3"):
        online = wait_for_health(watcher, topic, lambda p: p.status == "online")
        time.sleep(0.2)
    offline = wait_for_health(watcher, topic, lambda p: p.status == "offline")
    assert online.payload.version == "1.2.3"
    assert offline.payload.last_will is None and offline.payload.uptime_s > 0


SERVICE_SCRIPT = textwrap.dedent(
    """
    import sys, time
    from contracts.service import BusService
    BusService(sys.argv[1], sys.argv[2], port=int(sys.argv[3])).connect()
    print("ready", flush=True)
    time.sleep(60)
    """
)


@pytest.mark.parametrize(("role", "component"), [("brain", "brain"), ("body", "body")])
def test_killed_service_leaves_its_last_will(broker, watcher, role, component):
    topic = health_topic(component)
    process = subprocess.Popen(
        [sys.executable, "-c", SERVICE_SCRIPT, role, broker.passwords[role], str(broker.port)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "ready"
        wait_for_health(watcher, topic, lambda p: p.status == "online")
        killed_at = time.monotonic()
        process.send_signal(signal.SIGKILL)
        will = wait_for_health(watcher, topic, lambda p: p.last_will is True)
        assert time.monotonic() - killed_at < 2
    finally:
        process.kill()
        process.wait()
    assert will.payload.status == "offline" and will.payload.uptime_s == 0
    assert will.envelope.source == role


def test_last_will_is_retained_for_late_subscribers(broker, raw, watcher):
    topic = health_topic("brain")
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            SERVICE_SCRIPT,
            "brain",
            broker.passwords["brain"],
            str(broker.port),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert process.stdout.readline().strip() == "ready"
    process.send_signal(signal.SIGKILL)
    process.wait()
    wait_for_health(watcher, topic, lambda p: p.last_will is True)
    late = raw("recorder", broker.passwords["recorder"])
    late.subscribe(topic)
    deadline = time.monotonic() + 2
    while not late.received(topic) and time.monotonic() < deadline:
        time.sleep(0.02)
    (retained,) = late.received(topic)
    assert retained.retain and decode(topic, retained.payload).payload.last_will is True


def test_wrong_password_raises_on_connect(broker):
    with pytest.raises(BusError):
        BusService("body", "wrong", port=broker.port, timeout_s=2).connect()


# --- production configuration -------------------------------------------------------


def test_production_broker_has_no_test_only_roles(tmp_path, raw):
    test_dir = tmp_path / "test"
    test_passwords = generate(test_dir, "test", ["127.0.0.1:1"])
    prod = Broker(tmp_path / "prod", "prod")
    try:
        assert set(prod.passwords) == {"body", "brain", "recorder"}
        for role in ("sim", "replay", "eval"):
            client = RawClient(prod.port, role, test_passwords[role])
            try:
                assert not client.accepted
            finally:
                client.close()
        assert set(ROLES) - set(prod.passwords) == {"sim", "replay", "eval"}
    finally:
        prod.stop()
