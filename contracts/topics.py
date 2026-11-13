"""E0 topics and their payloads (docs/contratos/topicos-e0.md, v0.3)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from contracts.types import UUID4, Timestamp, WireModel

TOPICS_VERSION = "0.3"

UnitFloat = Annotated[float, Field(ge=0, le=1)]


class Payload(WireModel):
    def check_against_envelope(self, envelope_ts: datetime) -> None:
        """Rules that relate the payload to its envelope; raise ValueError to reject."""


class PersonEntered(Payload):
    track_id: str = Field(min_length=1)
    confidence: UnitFloat
    bbox: list[UnitFloat] = Field(min_length=4, max_length=4)
    first_seen_ts: Timestamp | None = None
    frame_ts: Timestamp | None = None

    @model_validator(mode="after")
    def _capture_order(self) -> "PersonEntered":
        if self.first_seen_ts and self.frame_ts and self.first_seen_ts > self.frame_ts:
            raise ValueError("first_seen_ts must not be after frame_ts")
        return self

    def check_against_envelope(self, envelope_ts: datetime) -> None:
        for name in ("first_seen_ts", "frame_ts"):
            value = getattr(self, name)
            if value is not None and value > envelope_ts:
                raise ValueError(f"{name} must not be after the envelope ts")


class PersonLeft(Payload):
    track_id: str = Field(min_length=1)
    duration_s: float = Field(ge=0)


class Say(Payload):
    say_id: UUID4
    text: str = Field(min_length=1)
    lang: Literal["es", "en", "pt"]
    priority: Literal["normal", "high"]


class SpeechStatus(Payload):
    say_id: UUID4
    state: Literal["started", "finished", "error"]
    error: str | None = None


class Health(Payload):
    status: Literal["online", "offline"]
    version: str = Field(min_length=1)
    uptime_s: float = Field(ge=0)
    last_will: bool | None = None

    @model_validator(mode="after")
    def _last_will_is_offline(self) -> "Health":
        if self.last_will and (self.status != "offline" or self.uptime_s != 0):
            raise ValueError("a last will must carry status offline and uptime_s 0")
        return self


@dataclass(frozen=True)
class TopicSpec:
    topic: str
    type: str
    payload: type[Payload]
    retained: bool = False


# Services that publish health. `sim` stands in for `body` and uses its topic.
HEALTH_COMPONENTS = ("body", "brain")
HEALTH_TYPE = "sys.health"


def health_topic(component: str) -> str:
    if component not in HEALTH_COMPONENTS:
        raise ValueError(f"{component!r} does not publish health in E0")
    return f"sancho/sys/{component}/health"


_SPECS = [
    TopicSpec("sancho/body/vision/evt/person_entered", "vision.person_entered", PersonEntered),
    TopicSpec("sancho/body/vision/evt/person_left", "vision.person_left", PersonLeft),
    TopicSpec("sancho/body/speech/cmd/say", "speech.say", Say),
    TopicSpec("sancho/body/speech/evt/status", "speech.status", SpeechStatus),
    *(TopicSpec(health_topic(c), HEALTH_TYPE, Health, retained=True) for c in HEALTH_COMPONENTS),
]

TOPICS: dict[str, TopicSpec] = {spec.topic: spec for spec in _SPECS}


def spec_for(topic: str) -> TopicSpec | None:
    return TOPICS.get(topic)
