"""Trace records (docs/contratos/trazas.md, v0.2), one JSON object per line."""

import threading
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, field_validator, model_validator

from contracts.types import UUID4, AuthoredModel, Timestamp, WireModel, check_version

TRACE_VERSION = "0.1"


class MessageRefs(AuthoredModel):
    """References to bus messages; extra keys are rejected so content is never copied."""

    message_ids: list[UUID4] = Field(default_factory=list)


class TraceRecord(WireModel):
    v: str
    ts: Timestamp
    trace_id: UUID4
    span_id: UUID4
    parent_span_id: UUID4 | None = None
    component: str = Field(min_length=1)
    kind: Literal["decision", "action", "error", "measurement"]
    name: str = Field(min_length=1)
    level: Literal["L0", "L1", "L2", "L3"]
    inputs: MessageRefs = Field(default_factory=MessageRefs)
    outputs: MessageRefs = Field(default_factory=MessageRefs)
    decision: str | None = None
    reason: str | None = None
    alternatives: list[str] = Field(default_factory=list)
    duration_ms: float = Field(ge=0)
    cost: None = None  # null in E0

    @field_validator("v")
    @classmethod
    def _supported_version(cls, value: str) -> str:
        return check_version(value, supported_major=0)

    @model_validator(mode="after")
    def _decisions_explain_themselves(self) -> "TraceRecord":
        if self.kind == "decision" and not (self.decision and self.reason):
            raise ValueError("a decision trace needs decision and reason")
        return self

    def to_jsonl(self) -> str:
        return self.model_dump_json() + "\n"


class InvalidTrace(Exception):
    pass


def parse_trace_line(line: str) -> TraceRecord:
    try:
        return TraceRecord.model_validate_json(line)
    except ValidationError as error:
        raise InvalidTrace(str(error)) from None


class TraceWriter:
    """Appends traces to `<directory>/<component>-<UTC day>.jsonl`, one file per day.

    Each record is validated (it is a TraceRecord) and flushed as it is written, so a
    crash loses at most the line being written.
    """

    def __init__(self, directory: Path, component: str):
        self.directory = Path(directory)
        self.component = component
        self._lock = threading.Lock()

    def path_for(self, record: TraceRecord) -> Path:
        return self.directory / f"{self.component}-{record.ts:%Y-%m-%d}.jsonl"

    def write(self, record: TraceRecord) -> None:
        if record.component != self.component:
            raise ValueError(f"trace from {record.component!r} in {self.component!r} writer")
        line = record.to_jsonl()
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            with self.path_for(record).open("a", encoding="utf-8") as file:
                file.write(line)


def read_traces(path: Path) -> list[TraceRecord]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [parse_trace_line(line) for line in lines if line.strip()]
