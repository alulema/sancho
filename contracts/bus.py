"""The only way components turn bus bytes into messages and back.

Every message published or received goes through `encode` or `decode`. A message
that does not validate raises `InvalidMessage`; `receive` turns that into a logged
rejection so a bad message never brings a component down.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from contracts.envelope import ENVELOPE_VERSION, Envelope
from contracts.topics import Payload, TopicSpec, spec_for
from contracts.types import utc_now

_LOG_EXCERPT_CHARS = 200

# topicos-e0.md v0.4: no message above 64 KiB. The broker enforces it on the whole
# MQTT packet; encode keeps a margin for the topic and the packet headers.
MAX_PACKET_BYTES = 65536
_PACKET_OVERHEAD_BYTES = 1024


class InvalidMessage(Exception):
    def __init__(self, topic: str, reason: str):
        super().__init__(f"{topic}: {reason}")
        self.topic = topic
        self.reason = reason


@dataclass(frozen=True)
class Message:
    topic: str
    envelope: Envelope
    payload: Payload

    @property
    def spec(self) -> TopicSpec:
        spec = spec_for(self.topic)
        assert spec is not None
        return spec


def _describe(error: ValidationError) -> str:
    parts = []
    for item in error.errors(include_url=False, include_input=False):
        where = ".".join(str(p) for p in item["loc"]) or "<root>"
        parts.append(f"{where}: {item['msg']}")
    return "; ".join(parts)


def _validate(topic: str, envelope: Envelope) -> Message:
    spec = spec_for(topic)
    if spec is None:
        raise InvalidMessage(topic, "unknown topic")
    if envelope.type != spec.type:
        raise InvalidMessage(topic, f"type {envelope.type!r} does not match topic ({spec.type!r})")
    try:
        payload = spec.payload.model_validate(envelope.payload)
        payload.check_against_envelope(envelope.ts)
    except ValidationError as error:
        raise InvalidMessage(topic, "payload: " + _describe(error)) from None
    except ValueError as error:
        raise InvalidMessage(topic, f"payload: {error}") from None
    return Message(topic, envelope, payload)


def make_message(
    topic: str,
    source: str,
    payload: Payload,
    *,
    trace_id: uuid.UUID | None = None,
    causation_id: uuid.UUID | None = None,
    ts: datetime | None = None,
) -> Message:
    """Builds a valid message; starts a new flow unless `trace_id` is given."""
    spec = spec_for(topic)
    if spec is None:
        raise InvalidMessage(topic, "unknown topic")
    try:
        envelope = Envelope(
            v=ENVELOPE_VERSION,
            id=uuid.uuid4(),
            ts=ts or utc_now(),
            source=source,
            type=spec.type,
            trace_id=trace_id or uuid.uuid4(),
            causation_id=causation_id,
            payload=payload.model_dump(mode="json", exclude_none=True),
        )
    except ValidationError as error:
        raise InvalidMessage(topic, _describe(error)) from None
    return _validate(topic, envelope)


def encode(message: Message) -> bytes:
    """Validates again and serializes, so nothing invalid reaches the bus.

    The payload goes out as it is in the envelope, including fields this version does
    not know, so a component can forward a message from a newer minor version intact.
    """
    _validate(message.topic, message.envelope)
    data = message.envelope.model_dump(mode="json", exclude_none=True)
    data["payload"] = message.envelope.payload
    encoded = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()
    if len(encoded) + len(message.topic.encode()) + _PACKET_OVERHEAD_BYTES > MAX_PACKET_BYTES:
        raise InvalidMessage(message.topic, f"message too large ({len(encoded)} bytes)")
    return encoded


def decode(topic: str, data: bytes | str) -> Message:
    try:
        envelope = Envelope.model_validate_json(data)
    except ValidationError as error:
        raise InvalidMessage(topic, "envelope: " + _describe(error)) from None
    return _validate(topic, envelope)


def receive(topic: str, data: bytes | str, logger: logging.Logger) -> Message | None:
    """Decodes, or logs the rejection and returns None. Never raises InvalidMessage."""
    try:
        return decode(topic, data)
    except InvalidMessage as error:
        text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
        excerpt = text[:_LOG_EXCERPT_CHARS] + ("…" if len(text) > _LOG_EXCERPT_CHARS else "")
        logger.warning(
            "rejected message on %s: %s",
            topic,
            error.reason,
            extra={"topic": topic, "reason": error.reason, "excerpt": excerpt},
        )
        return None
