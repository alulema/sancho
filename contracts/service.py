"""Bus connection for components: credentials, validation, health and last will.

Implements the health rules of docs/contratos/topicos-e0.md: services register a
retained last will in the common envelope when connecting, publish `online` on every
(re)connection and publish a real `offline` before a clean disconnect.
"""

import logging
import threading
import time
from collections.abc import Callable

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.reasoncodes import ReasonCode

from contracts.acl import HEALTH_OF_ROLE, ROLES, may_publish
from contracts.bus import Message, encode, make_message, receive
from contracts.topics import Health, health_topic

QOS = 1
Handler = Callable[[Message], None]


class BusError(Exception):
    pass


class PublishDenied(BusError):
    pass


class BusService:
    def __init__(
        self,
        role: str,
        password: str,
        *,
        host: str = "127.0.0.1",
        port: int = 1883,
        version: str = "0.0.0",
        logger: logging.Logger | None = None,
        timeout_s: float = 5.0,
    ):
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}")
        self.role = role
        self.version = version
        self.logger = logger or logging.getLogger(f"sancho.bus.{role}")
        self._host, self._port, self._timeout_s = host, port, timeout_s
        self._started = time.monotonic()
        self._health_topic = health_topic(HEALTH_OF_ROLE[role]) if role in HEALTH_OF_ROLE else None
        self._handlers: dict[str, Handler] = {}
        self._connected = threading.Event()
        self._connect_error: str | None = None
        self._acks: dict[int, ReasonCode | list[ReasonCode]] = {}
        self._unawaited: set[int] = set()  # acks nobody waits for (sent on reconnect)
        self._ack_ready = threading.Condition()

        self._client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=f"sancho-{role}-{id(self):x}",
            protocol=mqtt.MQTTv5,
        )
        self._client.username_pw_set(role, password)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_publish = self._on_ack
        self._client.on_subscribe = self._on_ack
        if self._health_topic:
            will = self._health(status="offline", uptime_s=0, last_will=True)
            self._client.will_set(will.topic, encode(will), qos=QOS, retain=True)

    # --- lifecycle --------------------------------------------------------------

    def connect(self) -> "BusService":
        self._client.connect(self._host, self._port, keepalive=10)
        self._client.loop_start()
        if not self._connected.wait(self._timeout_s) or self._connect_error:
            self._client.loop_stop()
            raise BusError(f"cannot connect as {self.role}: {self._connect_error or 'timeout'}")
        return self

    def close(self) -> None:
        """Clean shutdown: real `offline` first, so the broker drops the last will."""
        if self._health_topic and self._connected.is_set():
            self.publish(self._health(status="offline", uptime_s=self.uptime_s))
        self._client.disconnect()
        self._client.loop_stop()

    def __enter__(self) -> "BusService":
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def uptime_s(self) -> float:
        return round(time.monotonic() - self._started, 3)

    # --- messages ---------------------------------------------------------------

    def publish(self, message: Message) -> None:
        if not may_publish(self.role, message.topic):
            raise PublishDenied(f"{self.role} may not publish on {message.topic}")
        info = self._client.publish(
            message.topic, encode(message), qos=QOS, retain=message.spec.retained
        )
        reason = self._wait_ack(info.mid, lambda: info.wait_for_publish(self._timeout_s))
        if reason is not None and reason.is_failure:
            raise PublishDenied(f"broker refused {message.topic}: {reason}")

    def subscribe(self, pattern: str, handler: Handler) -> None:
        self._handlers[pattern] = handler
        result, mid = self._client.subscribe(pattern, qos=QOS)
        if result != mqtt.MQTT_ERR_SUCCESS:
            raise BusError(f"subscribe to {pattern} failed: {mqtt.error_string(result)}")
        reasons = self._wait_ack(mid)
        if not reasons or any(r.is_failure for r in reasons):
            del self._handlers[pattern]
            raise BusError(f"broker refused subscription to {pattern}: {reasons}")

    # --- internals ---------------------------------------------------------------

    def _health(self, **fields) -> Message:
        assert self._health_topic
        payload = Health(version=self.version, **fields)
        return make_message(self._health_topic, self.role, payload)

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            self._connect_error = str(reason_code)
            self._connected.set()
            return
        self._connect_error = None
        self._connected.set()
        # Runs on the network thread, so these acks cannot arrive before being marked.
        for pattern in self._handlers:
            self._unawaited.add(client.subscribe(pattern, qos=QOS)[1])
        if self._health_topic:
            online = self._health(status="online", uptime_s=self.uptime_s)
            info = client.publish(online.topic, encode(online), qos=QOS, retain=True)
            self._unawaited.add(info.mid)

    def _on_message(self, client, userdata, msg) -> None:
        message = receive(msg.topic, msg.payload, self.logger)
        if message is None:
            return
        for pattern, handler in list(self._handlers.items()):
            if mqtt.topic_matches_sub(pattern, msg.topic):
                try:
                    handler(message)
                except Exception:
                    # A handler bug must not stop the network loop.
                    self.logger.exception("handler for %s failed on %s", pattern, msg.topic)

    def _on_ack(self, client, userdata, mid, reason, properties) -> None:
        with self._ack_ready:
            if mid in self._unawaited:
                self._unawaited.discard(mid)
                if not isinstance(reason, list) and reason.is_failure:
                    self.logger.error("broker refused health message: %s", reason)
                return
            self._acks[mid] = reason
            self._ack_ready.notify_all()

    def _wait_ack(self, mid: int, wait: Callable[[], None] | None = None):
        if wait:
            wait()
        with self._ack_ready:
            if not self._ack_ready.wait_for(lambda: mid in self._acks, self._timeout_s):
                raise BusError(f"no acknowledgement from the broker for message {mid}")
            return self._acks.pop(mid)
