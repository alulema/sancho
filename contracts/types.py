"""Field types and base models shared by every contract (docs/contratos/README.md)."""

import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, PlainSerializer, PlainValidator, WithJsonSchema

_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}"
)


def truncate_to_ms(value: datetime) -> datetime:
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


def utc_now() -> datetime:
    """Current UTC time with the millisecond precision the contracts carry."""
    return truncate_to_ms(datetime.now(UTC))


def parse_timestamp(value: Any) -> datetime:
    """Accepts `2026-11-03T18:20:00.123Z` exactly, or an aware datetime built in code."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("datetime must be timezone-aware")
        return truncate_to_ms(value.astimezone(UTC))
    if not isinstance(value, str) or not _TIMESTAMP_RE.fullmatch(value):
        raise ValueError("timestamp must look like 2026-11-03T18:20:00.123Z (UTC, milliseconds)")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z").astimezone(UTC)


def format_timestamp(value: datetime) -> str:
    value = value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def parse_uuid4(value: Any) -> uuid.UUID:
    """Accepts a canonical UUID v4 string or a UUID v4 object."""
    if isinstance(value, uuid.UUID):
        if value.version != 4:
            raise ValueError("UUID must be version 4")
        return value
    if not isinstance(value, str) or not _UUID_RE.fullmatch(value):
        raise ValueError("must be a UUID v4 in canonical form")
    return uuid.UUID(value)


Timestamp = Annotated[
    datetime,
    PlainValidator(parse_timestamp),
    PlainSerializer(format_timestamp, return_type=str),
    WithJsonSchema({"type": "string", "format": "date-time"}),
]

UUID4 = Annotated[
    uuid.UUID,
    PlainValidator(parse_uuid4),
    PlainSerializer(str, return_type=str),
    WithJsonSchema({"type": "string", "format": "uuid"}),
]


def check_version(value: str, supported_major: int) -> str:
    """Contracts are `MAJOR.MINOR`; any minor of the supported major is compatible."""
    match = re.fullmatch(r"(\d+)\.(\d+)", value)
    if not match:
        raise ValueError("version must look like MAJOR.MINOR")
    if int(match.group(1)) != supported_major:
        raise ValueError(f"unsupported major version {match.group(1)}; expected {supported_major}")
    return value


class WireModel(BaseModel):
    """Bus messages and traces: strict types, unknown fields ignored."""

    model_config = ConfigDict(strict=True, extra="ignore", allow_inf_nan=False, frozen=True)


class AuthoredModel(BaseModel):
    """Files written by people (bench cases): strict types, unknown fields rejected."""

    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False, frozen=True)
