"""Rule L0 of E0: greet whoever enters, unless someone was greeted in the last N minutes.

A pure decision on the events themselves: the window is measured with the `ts` of
the events, not with a local clock (docs/contratos/grabaciones.md), so a replayed
session takes the same decisions. The window starts at the entry whose greeting was
actually published (`commit`): if publishing fails, the next entry tries again.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
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
    at: datetime  # ts of the event decided on


def _minutes(value: float) -> str:
    text = f"{value:g}"
    return f"{text} minute" if text == "1" else f"{text} minutes"


class Greeter:
    def __init__(self, config: BrainConfig):
        self.config = config
        self._last_greeting: datetime | None = None

    def decide(self, entered: Message) -> Decision:
        now = entered.envelope.ts
        window = _minutes(self.config.greeting_window_min)
        since = None
        if self._last_greeting is not None:
            # An event older than the last greeting (out of order) counts as inside.
            since = max((now - self._last_greeting).total_seconds(), 0.0)
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
        """The greeting went out: the window starts at the ts of that entry."""
        if decision.say is not None:
            self._last_greeting = decision.at
