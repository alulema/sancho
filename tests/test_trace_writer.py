"""Trace files: one per component and UTC day, validated line by line."""

import uuid
from datetime import UTC, datetime

import pytest

from contracts.traces import TRACE_VERSION, TraceRecord, TraceWriter, read_traces


def record(component="brain", ts=datetime(2026, 11, 13, 23, 59, 59, 999000, tzinfo=UTC)):
    return TraceRecord(
        v=TRACE_VERSION, ts=ts, trace_id=uuid.uuid4(), span_id=uuid.uuid4(),
        component=component, kind="measurement", name="probe", level="L0", duration_ms=1.0,
    )  # fmt: skip


def test_writes_one_file_per_component_and_utc_day(tmp_path):
    writer = TraceWriter(tmp_path / "traces", "brain")
    late = record()
    early = record(ts=datetime(2026, 11, 14, 0, 0, 0, tzinfo=UTC))
    writer.write(late)
    writer.write(early)
    writer.write(late)
    assert sorted(p.name for p in (tmp_path / "traces").iterdir()) == [
        "brain-2026-11-13.jsonl", "brain-2026-11-14.jsonl",
    ]  # fmt: skip
    assert read_traces(tmp_path / "traces" / "brain-2026-11-13.jsonl") == [late, late]


def test_refuses_traces_of_another_component(tmp_path):
    with pytest.raises(ValueError):
        TraceWriter(tmp_path, "brain").write(record(component="body"))
