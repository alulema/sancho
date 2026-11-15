"""Rule L0 of E0: greet whoever enters, unless someone was greeted in the last N minutes.

A pure decision with an injected clock, so it is tested without a bus or real time.
The window starts when a greeting is actually published (`commit`): if publishing
fails, the next entry tries again.
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from contracts.bus import Message, make_message
from contracts.topics import Say
from contracts.types import AuthoredModel

SAY = "sancho/body/speech/cmd/say"
RULE = "greet_on_entry"
GREET, IGNORE = "say_greeting", "ignore"


class BrainConfig(AuthoredModel):
    """What `given.config` of a bench case can set (docs/contratos/casos-banco.md)."""

    greeting_window_min: float = Field(default=10, ge=0)
    greeting_text: str = Field(default="¡Hola! Qué gusto verte por el estudio.", min_length=1)
    lang: Literal["es", "en", "pt"] = "es"


@dataclass(frozen=True)
class Decision:
    decision: str
    reason: str
    alternatives: list[str]
    say: Message | None
    at: float  # clock reading when decided


def _minutes(value: float) -> str:
    text = f"{value:g}"
    return f"{text} minute" if text == "1" else f"{text} minutes"


class Greeter:
    def __init__(self, config: BrainConfig, clock: Callable[[], float] = time.monotonic):
        self.config = config
        self._clock = clock
        self._last_greeting: float | None = None

    def decide(self, entered: Message) -> Decision:
        now = self._clock()
        window = _minutes(self.config.greeting_window_min)
        since = None if self._last_greeting is None else now - self._last_greeting
        if since is not None and since < self.config.greeting_window_min * 60:
            reason = f"greeted {since:.1f} s ago, within the window of {window}"
            return Decision(IGNORE, reason, [GREET], None, now)
        say = make_message(
            SAY,
            "brain",
            Say(
                say_id=uuid.uuid4(),
                text=self.config.greeting_text,
                lang=self.config.lang,
                priority="normal",
            ),
            trace_id=entered.envelope.trace_id,
            causation_id=entered.envelope.id,
        )
        reason = (
            "no greeting since start"
            if since is None
            else f"no greeting in the last {window} (last {since:.1f} s ago)"
        )
        return Decision(GREET, reason, [IGNORE], say, now)

    def commit(self, decision: Decision) -> None:
        """The greeting went out: the window starts at the moment it was decided."""
        if decision.say is not None:
            self._last_greeting = decision.at
