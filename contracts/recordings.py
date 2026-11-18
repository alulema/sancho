"""Bus recordings (docs/contratos/grabaciones.md, v0.1), one JSON object per line.

The recorder keeps everything it receives without validating it: a JSON object goes
in `message` (even if it is not a valid envelope), anything else in `raw`.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError, field_validator, model_validator

from contracts.types import WireModel, check_version

REC_VERSION = "0.1"


class RecordLine(WireModel):
    rec_v: str
    t_ms: int = Field(ge=0)
    topic: str = Field(min_length=1)
    retained: bool
    message: dict[str, Any] | None = None
    raw: str | None = None

    @field_validator("rec_v")
    @classmethod
    def _supported_version(cls, value: str) -> str:
        return check_version(value, supported_major=0)

    @model_validator(mode="after")
    def _one_body(self) -> "RecordLine":
        if (self.message is None) == (self.raw is None):
            raise ValueError("a recorded line needs exactly one of message or raw")
        return self

    def to_jsonl(self) -> str:
        return self.model_dump_json(exclude_none=True) + "\n"

    def data(self) -> bytes:
        """The bytes to publish again: the object re-serialized, or the raw text."""
        if self.message is not None:
            return json.dumps(self.message, separators=(",", ":"), ensure_ascii=False).encode()
        assert self.raw is not None
        return self.raw.encode()


def _reject_constant(name: str):
    raise ValueError(f"non-standard JSON constant {name}")


def record(t_ms: int, topic: str, data: bytes, retained: bool) -> RecordLine:
    text = data.decode("utf-8", "replace")
    try:
        parsed = json.loads(text, parse_constant=_reject_constant)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        return RecordLine(rec_v=REC_VERSION, t_ms=t_ms, topic=topic, retained=retained,
                          message=parsed)  # fmt: skip
    return RecordLine(rec_v=REC_VERSION, t_ms=t_ms, topic=topic, retained=retained, raw=text)


class InvalidRecording(Exception):
    pass


def read_recording(path: Path) -> list[RecordLine]:
    lines = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            lines.append(RecordLine.model_validate_json(line))
        except ValidationError as error:
            raise InvalidRecording(f"{path}:{number}: {error}") from None
    return lines
