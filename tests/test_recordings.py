"""T9: recording format, what replay publishes and how, and decision comparison."""

import json
import threading
import time
import uuid
from datetime import timedelta

import pytest

from contracts.bus import decode, encode, make_message
from contracts.recordings import InvalidRecording, RecordLine, read_recording, record
from contracts.topics import Health, PersonEntered, Say, health_topic
from contracts.traces import TRACE_VERSION, MessageRefs, TraceRecord
from contracts.types import parse_timestamp, utc_now
from sim.recorder import Recorder
from sim.replay import play, rewrite, selected
from sim.rerun import differences
from tests.contract_docs import code_blocks

ENTERED = "sancho/body/vision/evt/person_entered"
SAY = "sancho/body/speech/cmd/say"


def entered_bytes(track="t1", ts=None):
    payload = PersonEntered(track_id=track, confidence=0.9, bbox=[0.4, 0.3, 0.2, 0.3])
    return encode(make_message(ENTERED, "body", payload, ts=ts))


# --- format -----------------------------------------------------------------------


def test_contract_examples_parse(tmp_path):
    (block,) = code_blocks("grabaciones.md", "json")
    path = tmp_path / "example.jsonl"
    path.write_text(block)
    good, broken = read_recording(path)
    assert good.message["type"] == "vision.person_entered" and good.raw is None
    assert broken.raw == "{esto no es JSON" and broken.message is None


def test_json_objects_are_kept_as_message_even_if_invalid():
    line = record(10, ENTERED, b'{"not": "an envelope"}', False)
    assert line.message == {"not": "an envelope"} and line.raw is None


@pytest.mark.parametrize("data", [b"{broken", b"[1, 2]", b'"text"', b'{"a": NaN}', b"\xff\xfe"])
def test_anything_else_is_kept_as_raw_text(data):
    line = record(0, ENTERED, data, False)
    assert line.message is None and line.raw == data.decode("utf-8", "replace")


def test_a_line_needs_exactly_one_body():
    with pytest.raises(ValueError):
        RecordLine(rec_v="0.1", t_ms=0, topic=ENTERED, retained=False)
    with pytest.raises(ValueError):
        RecordLine(rec_v="0.1", t_ms=0, topic=ENTERED, retained=False, message={}, raw="x")


def test_invalid_line_is_reported_with_its_number(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(record(0, ENTERED, b"x", False).to_jsonl() + '{"rec_v": "0.1"}\n')
    with pytest.raises(InvalidRecording, match=r"bad\.jsonl:2"):
        read_recording(path)


def test_recorder_writes_lines_with_relative_times(tmp_path):
    recorder = Recorder(tmp_path / "rec" / "session.jsonl")
    recorder(ENTERED, entered_bytes(), False)
    time.sleep(0.05)
    recorder(health_topic("brain"), b"{oops", True)
    recorder.close()
    first, second = read_recording(tmp_path / "rec" / "session.jsonl")
    assert first.t_ms < second.t_ms and second.t_ms - first.t_ms >= 50
    assert (second.retained, second.raw) == (True, "{oops")


# --- replay -----------------------------------------------------------------------


def lines_of(*records):
    return [record(*r) for r in records]


def test_only_live_events_are_replayed():
    say_payload = Say(say_id=uuid.uuid4(), text="Hola", lang="es", priority="normal")
    say = encode(make_message(SAY, "brain", say_payload))
    health_payload = Health(status="online", version="1", uptime_s=0)
    health = encode(make_message(health_topic("brain"), "brain", health_payload))
    lines = lines_of(
        (0, ENTERED, entered_bytes(), True),  # retained: not part of the session
        (1, ENTERED, entered_bytes(), False),
        (2, SAY, say, False),  # command: output of the brain under test
        (3, health_topic("brain"), health, False),
        (4, "sancho/body/vision/evt/person_left", b"{broken", False),
    )
    assert [i.t_ms for i in selected(lines)] == [1, 4]


def test_rewrite_shifts_ts_and_changes_only_source():
    original = record(0, ENTERED, entered_bytes(), False)
    data = json.loads(rewrite(original, timedelta(hours=2)))
    before = original.message
    assert parse_timestamp(data["ts"]) - parse_timestamp(before["ts"]) == timedelta(hours=2)
    assert data["source"] == "replay"
    for key in ("id", "trace_id", "type", "payload", "v"):
        assert data[key] == before[key]
    assert decode(ENTERED, json.dumps(data)).envelope.source == "replay"  # still valid


def test_rewrite_leaves_raw_text_and_unparseable_ts_alone():
    assert rewrite(record(0, ENTERED, b"{broken", False), timedelta(1)) == b"{broken"
    weird = json.loads(rewrite(record(0, ENTERED, b'{"ts": "yesterday"}', False), timedelta(1)))
    assert weird == {"ts": "yesterday", "source": "replay"}


class RawSink:
    def __init__(self):
        self.sent = []

    def publish_raw(self, topic, data):
        self.sent.append((time.monotonic(), topic, data))


def test_play_keeps_relative_times_and_one_offset():
    old = utc_now() - timedelta(days=1)
    lines = lines_of(
        (1000, ENTERED, entered_bytes("t1", old), False),
        (1300, ENTERED, entered_bytes("t2", old + timedelta(milliseconds=300)), False),
    )
    sink, before = RawSink(), utc_now()
    assert play(sink, lines, threading.Event()) == 2
    (t1, _, first), (t2, _, second) = sink.sent
    assert 0.28 <= t2 - t1 <= 0.5
    ts1 = parse_timestamp(json.loads(first)["ts"])
    ts2 = parse_timestamp(json.loads(second)["ts"])
    assert ts2 - ts1 == timedelta(milliseconds=300)  # distances are exact
    assert abs((ts1 - before).total_seconds()) < 0.5  # the session now starts now


def test_play_stops_when_asked():
    lines = lines_of(
        (0, ENTERED, entered_bytes(), False), (60_000, ENTERED, entered_bytes(), False)
    )
    stop, sink = threading.Event(), RawSink()
    threading.Timer(0.1, stop.set).start()
    play(sink, lines, stop)
    assert len(sink.sent) == 1


# --- comparison -------------------------------------------------------------------


def decision(choice, inputs, outputs=()):
    return TraceRecord(
        v=TRACE_VERSION, ts=utc_now(), trace_id=uuid.uuid4(), span_id=uuid.uuid4(),
        component="brain", kind="decision", name="greet_on_entry", level="L0",
        inputs=MessageRefs(message_ids=inputs), outputs=MessageRefs(message_ids=list(outputs)),
        decision=choice, reason="r", duration_ms=1,
    )  # fmt: skip


def test_same_decisions_ignore_outputs_and_reasons():
    a, b = uuid.uuid4(), uuid.uuid4()
    original = [decision("say_greeting", [a], [uuid.uuid4()]), decision("ignore", [b])]
    replayed = [decision("say_greeting", [a], [uuid.uuid4()]), decision("ignore", [b])]
    assert differences(original, replayed) == []


def test_different_decision_order_or_count_is_reported():
    a, b = uuid.uuid4(), uuid.uuid4()
    original = [decision("say_greeting", [a]), decision("ignore", [b])]
    assert len(differences(original, [decision("say_greeting", [a]),
                                      decision("say_greeting", [b])])) == 1  # fmt: skip
    assert len(differences(original, [decision("say_greeting", [a])])) == 1
    assert len(differences(original, list(reversed(original)))) == 2
