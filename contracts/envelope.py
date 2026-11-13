"""Common message envelope (docs/contratos/sobre.md, v0.1)."""

from typing import Any

from pydantic import Field, field_validator

from contracts.types import UUID4, Timestamp, WireModel, check_version

ENVELOPE_VERSION = "0.1"


class Envelope(WireModel):
    v: str
    id: UUID4
    ts: Timestamp
    source: str = Field(min_length=1)
    type: str = Field(min_length=1)
    trace_id: UUID4
    causation_id: UUID4 | None = None
    payload: dict[str, Any]
    # Reserved for E4 (signed identity on the bus); accepted and ignored in E0.
    sig: str | None = None

    @field_validator("v")
    @classmethod
    def _supported_version(cls, value: str) -> str:
        return check_version(value, supported_major=0)
