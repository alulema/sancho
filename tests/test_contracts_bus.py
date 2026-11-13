"""Envelope and E0 topics: valid and invalid messages (T5)."""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from contracts.bus import InvalidMessage, decode, encode, make_message, receive
from contracts.envelope import Envelope
from contracts.topics import (
    TOPICS,
    Health,
    PersonEntered,
    PersonLeft,
    Say,
    SpeechStatus,
    health_topic,
)
from contracts.types import format_timestamp
from tests.contract_docs import code_blocks

ENTERED = "sancho/body/vision/evt/person_entered"
LEFT = "sancho/body/vision/evt/person_left"
SAY = "sancho/body/speech/cmd/say"
STATUS = "sancho/body/speech/evt/status"
TS = datetime(2026, 11, 3, 18, 20, 0, 123000, tzinfo=UTC)
MS = timedelta(milliseconds=1)

VALID_PAYLOADS = {
    ENTERED: PersonEntered(track_id="t1", confidence=0.92, bbox=[0.4, 0.3, 0.2, 0.3]),
    LEFT: PersonLeft(track_id="t1", duration_s=3),
    SAY: Say(say_id=uuid.uuid4(), text="Hola", lang="es", priority="normal"),
    STATUS: SpeechStatus(say_id=uuid.uuid4(), state="started"),
    health_topic("body"): Health(status="online", version="0.1.0", uptime_s=12.5),
    health_topic("brain"): Health(status="offline", version="0.1.0", uptime_s=0, last_will=True),
}


def raw_message(topic: str, **overrides) -> dict:
    """A valid message as a dict, to break one field at a time."""
    message = json.loads(encode(make_message(topic, "test", VALID_PAYLOADS[topic], ts=TS)))
    payload_overrides = overrides.pop("payload", {})
    message.update(overrides)
    message["payload"].update(payload_overrides)
    return message


def as_bytes(message: dict) -> bytes:
    return json.dumps(message).encode()


# --- valid messages ---------------------------------------------------------------


def test_every_e0_topic_has_a_valid_example():
    assert set(VALID_PAYLOADS) == set(TOPICS)


@pytest.mark.parametrize("topic", sorted(VALID_PAYLOADS))
def test_round_trip(topic):
    message = make_message(topic, "test", VALID_PAYLOADS[topic])
    decoded = decode(topic, encode(message))
    assert decoded.envelope == message.envelope
    assert decoded.payload == VALID_PAYLOADS[topic]


@pytest.mark.parametrize("spec", TOPICS.values(), ids=lambda s: s.topic)
def test_type_follows_the_topic_naming_rule(spec):
    parts = spec.topic.split("/")
    if parts[1] == "sys":
        assert spec.type == "sys.health" and spec.retained
    else:
        _, owner, capability, kind, name = parts
        assert owner == "body" and kind in ("evt", "cmd")
        assert spec.type == f"{capability}.{name}" and not spec.retained


def test_envelope_example_from_the_contract_validates():
    (example,) = code_blocks("sobre.md", "json")
    envelope = Envelope.model_validate_json(example)
    assert envelope.type == "vision.person_entered"


def test_recording_examples_carry_valid_messages():
    (block,) = code_blocks("grabaciones.md", "json")
    line = block.splitlines()[0]
    record = json.loads(line)
    decoded = decode(record["topic"], json.dumps(record["message"]))
    assert decoded.payload.track_id == "t1"


def test_timestamps_are_serialized_with_milliseconds_and_z():
    message = make_message(ENTERED, "test", VALID_PAYLOADS[ENTERED], ts=TS.replace(microsecond=0))
    assert json.loads(encode(message))["ts"] == "2026-11-03T18:20:00.000Z"


def test_new_message_starts_a_flow_and_a_reply_continues_it():
    first = make_message(ENTERED, "body", VALID_PAYLOADS[ENTERED])
    reply = make_message(
        SAY,
        "brain",
        VALID_PAYLOADS[SAY],
        trace_id=first.envelope.trace_id,
        causation_id=first.envelope.id,
    )
    assert reply.envelope.trace_id == first.envelope.trace_id
    assert reply.envelope.causation_id == first.envelope.id
    assert first.envelope.id != reply.envelope.id


def test_optional_fields_are_omitted_not_null():
    data = json.loads(encode(make_message(STATUS, "body", VALID_PAYLOADS[STATUS])))
    assert "causation_id" not in data and "sig" not in data and "error" not in data["payload"]


def test_unknown_fields_are_ignored_and_forwarded():
    message = raw_message(ENTERED, extra_envelope=1, payload={"new_in_minor": "x"})
    decoded = decode(ENTERED, as_bytes(message))
    assert json.loads(encode(decoded))["payload"]["new_in_minor"] == "x"


def test_newer_minor_version_is_accepted():
    assert decode(ENTERED, as_bytes(raw_message(ENTERED, v="0.7")))


def test_latency_marks_in_order_are_accepted():
    ts = "2026-11-03T18:20:00.123Z"
    marks = {"first_seen_ts": "2026-11-03T18:19:59.900Z", "frame_ts": ts}
    decoded = decode(ENTERED, as_bytes(raw_message(ENTERED, ts=ts, payload=marks)))
    assert decoded.payload.frame_ts == decoded.envelope.ts


# --- invalid messages -------------------------------------------------------------

BAD_ENVELOPES = {
    "not json": b"{esto no es JSON",
    "json array": b"[]",
    "not utf-8": b"\xff\xfe",
    "missing trace_id": {"trace_id": None},
    "major version 1": {"v": "1.0"},
    "version not a string": {"v": 0.1},
    "ts without ms": {"ts": "2026-11-03T18:20:00Z"},
    "ts with microseconds": {"ts": "2026-11-03T18:20:00.123456Z"},
    "ts with offset": {"ts": "2026-11-03T18:20:00.123+00:00"},
    "ts not a date": {"ts": "2026-13-03T18:20:00.123Z"},
    "id not uuid": {"id": "abc"},
    "id uuid v1": {"id": str(uuid.uuid1())},
    "id without hyphens": {"id": uuid.uuid4().hex},
    "empty source": {"source": ""},
    "payload not an object": {"payload": [1, 2]},
}


@pytest.mark.parametrize("case", BAD_ENVELOPES, ids=str)
def test_invalid_envelope_is_rejected(case):
    bad = BAD_ENVELOPES[case]
    if isinstance(bad, dict):
        message = raw_message(LEFT)
        for key, value in bad.items():
            if value is None:
                del message[key]
            else:
                message[key] = value
        bad = as_bytes(message)
    with pytest.raises(InvalidMessage) as error:
        decode(LEFT, bad)
    assert error.value.topic == LEFT


BAD_PAYLOADS = [
    (ENTERED, {"confidence": "0.9"}),
    (ENTERED, {"confidence": 1.2}),
    (ENTERED, {"confidence": True}),
    (ENTERED, {"bbox": [0.4, 0.3, 0.2]}),
    (ENTERED, {"bbox": [0.4, 0.3, 0.2, 1.5]}),
    (ENTERED, {"track_id": ""}),
    (ENTERED, {"first_seen_ts": format_timestamp(TS), "frame_ts": format_timestamp(TS - MS)}),
    (ENTERED, {"frame_ts": format_timestamp(TS + timedelta(seconds=1))}),
    (LEFT, {"duration_s": -1}),
    (SAY, {"lang": "fr"}),
    (SAY, {"priority": "urgent"}),
    (SAY, {"text": ""}),
    (SAY, {"say_id": "not-a-uuid"}),
    (STATUS, {"state": "paused"}),
    (health_topic("body"), {"status": "online", "last_will": True}),
    (health_topic("body"), {"uptime_s": 5, "status": "offline", "last_will": True}),
]


@pytest.mark.parametrize(("topic", "change"), BAD_PAYLOADS, ids=lambda x: str(x))
def test_invalid_payload_is_rejected(topic, change):
    with pytest.raises(InvalidMessage, match="payload"):
        decode(topic, as_bytes(raw_message(topic, payload=change)))


def test_nan_is_rejected():
    text = encode(make_message(ENTERED, "t", VALID_PAYLOADS[ENTERED])).decode()
    with pytest.raises(InvalidMessage):
        decode(ENTERED, text.replace('"confidence":0.92', '"confidence":NaN'))


def test_missing_payload_field_is_rejected():
    message = raw_message(LEFT)
    del message["payload"]["duration_s"]
    with pytest.raises(InvalidMessage, match="duration_s"):
        decode(LEFT, as_bytes(message))


def test_oversized_message_cannot_be_encoded():
    payload = Say(say_id=uuid.uuid4(), text="a" * 70_000, lang="es", priority="normal")
    with pytest.raises(InvalidMessage, match="too large"):
        encode(make_message(SAY, "brain", payload))


def test_type_must_match_topic():
    with pytest.raises(InvalidMessage, match="does not match"):
        decode(LEFT, as_bytes(raw_message(ENTERED)))


@pytest.mark.parametrize("topic", ["sancho/body/vision/evt/unknown", "sancho/sys/sim/health"])
def test_unknown_topic_is_rejected(topic):
    with pytest.raises(InvalidMessage, match="unknown topic"):
        decode(topic, as_bytes(raw_message(LEFT)))


def test_cannot_build_an_invalid_message():
    with pytest.raises(InvalidMessage):
        make_message(ENTERED, "body", VALID_PAYLOADS[LEFT])
    with pytest.raises(InvalidMessage, match="unknown topic"):
        make_message("sancho/elsewhere", "body", VALID_PAYLOADS[LEFT])
    with pytest.raises(InvalidMessage):
        make_message(LEFT, "", VALID_PAYLOADS[LEFT])


def test_health_topic_only_for_services():
    with pytest.raises(ValueError):
        health_topic("sim")


# --- rejection is logged, not raised ----------------------------------------------


def test_receive_logs_and_returns_none_for_invalid(caplog):
    logger = logging.getLogger("test.receive")
    with caplog.at_level(logging.WARNING, logger="test.receive"):
        assert receive(ENTERED, b"{esto no es JSON", logger) is None
    (record,) = caplog.records
    assert record.topic == ENTERED and "envelope" in record.reason
    assert record.excerpt == "{esto no es JSON"


def test_receive_truncates_long_input_in_the_log(caplog):
    logger = logging.getLogger("test.receive")
    with caplog.at_level(logging.WARNING, logger="test.receive"):
        receive(ENTERED, "x" * 10_000, logger)
    assert len(caplog.records[0].excerpt) <= 201


def test_receive_returns_valid_messages_and_keeps_going(caplog):
    logger = logging.getLogger("test.receive")
    good = encode(make_message(ENTERED, "body", VALID_PAYLOADS[ENTERED]))
    results = [receive(ENTERED, data, logger) for data in (b"garbage", good, b"{}", good)]
    assert [r is not None for r in results] == [False, True, False, True]
