"""Evaluation bench cases (docs/contratos/casos-banco.md, v0.2), one YAML file each.

The runner wraps `publish` payloads in an envelope without validating them, so
invalid messages can be injected on purpose; here they are plain dictionaries.
"""

from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import AfterValidator, Field, ValidationError, field_validator, model_validator

from contracts.types import AuthoredModel, check_version

CASES_VERSION = "0.2"

JsonScalar = str | int | float | bool | None


def _bus_topic(value: str) -> str:
    if not value.startswith("sancho/") or any(c in value for c in "+#"):
        raise ValueError("topic must be a concrete topic under sancho/")
    return value


Topic = Annotated[str, AfterValidator(_bus_topic)]


class Publish(AuthoredModel):
    topic: Topic
    payload: dict[str, Any]


class PublishRaw(AuthoredModel):
    topic: Topic
    text: str


class Stop(AuthoredModel):
    component: str = Field(min_length=1)
    mode: Literal["abrupt", "clean"]


class Start(AuthoredModel):
    component: str = Field(min_length=1)


class Step(AuthoredModel):
    at_ms: int = Field(ge=0)
    publish: Publish | None = None
    publish_raw: PublishRaw | None = None
    stop: Stop | None = None
    start: Start | None = None

    @model_validator(mode="after")
    def _exactly_one_action(self) -> "Step":
        actions = [self.publish, self.publish_raw, self.stop, self.start]
        if sum(a is not None for a in actions) != 1:
            raise ValueError("a step needs exactly one of publish, publish_raw, stop, start")
        return self


class Expectation(AuthoredModel):
    topic: Topic
    count: int = Field(ge=0)
    within_ms: int = Field(gt=0)
    payload: dict[str, Any] | None = None


class Prohibition(AuthoredModel):
    topic: Topic
    count_gt: int = Field(ge=0)
    within_ms: int = Field(gt=0)
    payload: dict[str, Any] | None = None


class Given(AuthoredModel):
    config: dict[str, JsonScalar] = Field(default_factory=dict)


class Case(AuthoredModel):
    id: str = Field(pattern=r"^e\d+-[a-z0-9]+(-[a-z0-9]+)*$")
    version: str
    description: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    lang: Literal["es", "en", "pt"]
    given: Given = Field(default_factory=Given)
    when: list[Step] = Field(min_length=1)
    expect: list[Expectation] = Field(default_factory=list)
    forbid: list[Prohibition] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def _supported_version(cls, value: str) -> str:
        return check_version(value, supported_major=0)

    @model_validator(mode="after")
    def _well_formed(self) -> "Case":
        times = [step.at_ms for step in self.when]
        if times != sorted(times):
            raise ValueError("steps must be ordered by at_ms")
        if not self.expect and not self.forbid:
            raise ValueError("a case needs at least one expect or forbid")
        return self


class InvalidCase(Exception):
    pass


def load_case(path: Path) -> Case:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return Case.model_validate(data)
    except (yaml.YAMLError, ValidationError) as error:
        raise InvalidCase(f"{path}: {error}") from None
