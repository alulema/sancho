"""Trace records: valid and invalid (T5)."""

import json
import uuid

import pytest

from contracts.traces import InvalidTrace, TraceRecord, parse_trace_line
from tests.contract_docs import code_blocks

(EXAMPLE,) = code_blocks("trazas.md", "json")


def example(**overrides) -> str:
    data = json.loads(EXAMPLE)
    data.update(overrides)
    return json.dumps(data)


def test_contract_example_validates():
    record = parse_trace_line(EXAMPLE)
    assert record.name == "greet_on_entry" and record.kind == "decision"


def test_jsonl_round_trip_is_one_line():
    record = parse_trace_line(EXAMPLE)
    line = record.to_jsonl()
    assert line.endswith("\n") and line.count("\n") == 1
    assert parse_trace_line(line) == record
    assert json.loads(line)["ts"] == "2026-11-03T18:20:00.180Z"


def test_action_trace_needs_no_decision():
    record = TraceRecord(
        v="0.1",
        ts="2026-11-03T18:20:00.200Z",
        trace_id=uuid.uuid4(),
        span_id=uuid.uuid4(),
        component="body",
        kind="action",
        name="speak",
        level="L0",
        duration_ms=850,
    )
    assert record.inputs.message_ids == [] and record.cost is None


def test_unknown_fields_are_ignored():
    assert parse_trace_line(example(new_in_minor=True))


BAD = {
    "decision without reason": {"reason": None},
    "unknown kind": {"kind": "thought"},
    "unknown level": {"level": "L4"},
    "negative duration": {"duration_ms": -1},
    "cost in E0": {"cost": 0.01},
    "copied content in inputs": {"inputs": {"message_ids": [], "payload": {"text": "hola"}}},
    "message id not uuid": {"outputs": {"message_ids": ["m1"]}},
    "ts without ms": {"ts": "2026-11-03T18:20:00Z"},
    "major version": {"v": "1.0"},
}


@pytest.mark.parametrize("case", BAD, ids=str)
def test_invalid_trace_is_rejected(case):
    with pytest.raises(InvalidTrace):
        parse_trace_line(example(**BAD[case]))


def test_broken_line_is_rejected():
    with pytest.raises(InvalidTrace):
        parse_trace_line('{"v": "0.1",')
