"""Scripts for the simulated camera: who enters and leaves, and when.

```yaml
description: Two entries within the greeting window.
steps:
  - at_ms: 0
    enter: { track_id: t1 }
  - at_ms: 3000
    leave: { track_id: t1 }
```

Each step has `at_ms` (from the start of the script) and exactly one of `enter` or
`leave`. A track must enter before it leaves and cannot enter twice while inside.
"""

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import Field, ValidationError, model_validator

from contracts.types import AuthoredModel

Unit = Annotated[float, Field(ge=0, le=1)]


class Enter(AuthoredModel):
    track_id: str = Field(min_length=1)
    confidence: Unit = 0.9
    bbox: list[Unit] = Field(default=[0.4, 0.3, 0.2, 0.3], min_length=4, max_length=4)
    # Time between the first frame that saw the person and the one that confirmed the
    # entry; the simulated camera puts it in first_seen_ts.
    hysteresis_ms: int = Field(default=300, ge=0)


class Leave(AuthoredModel):
    track_id: str = Field(min_length=1)


class ScriptStep(AuthoredModel):
    at_ms: int = Field(ge=0)
    enter: Enter | None = None
    leave: Leave | None = None

    @model_validator(mode="after")
    def _one_action(self) -> "ScriptStep":
        if (self.enter is None) == (self.leave is None):
            raise ValueError("a step needs exactly one of enter or leave")
        return self


class Script(AuthoredModel):
    description: str = Field(min_length=1)
    steps: list[ScriptStep] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> "Script":
        inside: set[str] = set()
        previous = 0
        for step in self.steps:
            if step.at_ms < previous:
                raise ValueError("steps must be ordered by at_ms")
            previous = step.at_ms
            if step.enter:
                if step.enter.track_id in inside:
                    raise ValueError(f"{step.enter.track_id} enters twice without leaving")
                inside.add(step.enter.track_id)
            else:
                assert step.leave is not None
                if step.leave.track_id not in inside:
                    raise ValueError(f"{step.leave.track_id} leaves without having entered")
                inside.discard(step.leave.track_id)
        return self

    @property
    def duration_ms(self) -> int:
        return self.steps[-1].at_ms


class InvalidScript(Exception):
    pass


def load_script(path: Path) -> Script:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return Script.model_validate(data)
    except (yaml.YAMLError, ValidationError) as error:
        raise InvalidScript(f"{path}: {error}") from None
