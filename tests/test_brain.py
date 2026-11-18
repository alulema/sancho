"""T7: the greeting rule, its window and the trace of each decision (no bus needed)."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from brain.greeter import GREET, IGNORE, SAY, BrainConfig, Greeter
from brain.service import ENTERED, Brain
from contracts.bus import decode, encode, make_message
from contracts.service import BusError
from contracts.topics import PersonEntered
from contracts.traces import TraceWriter, read_traces
from contracts.types import utc_now


class Clock:
    """Event time: each entry is stamped with `now`, which the tests move forward."""

    def __init__(self):
        self.at = datetime(2026, 11, 13, 18, 0, tzinfo=UTC)

    def advance(self, seconds: float) -> None:
        self.at += timedelta(seconds=seconds)


class FakeService:
    def __init__(self, fail: bool = False):
        self.published = []
        self.fail = fail

    def publish(self, message):
        if self.fail:
            raise BusError("no acknowledgement from the broker")
        self.published.append(decode(message.topic, encode(message)))


CLOCK = Clock()


def entered(track="t1", at=None):
    payload = PersonEntered(track_id=track, confidence=0.9, bbox=[0.4, 0.3, 0.2, 0.3])
    return make_message(ENTERED, "body", payload, ts=at or CLOCK.at)


@pytest.fixture
def clock():
    CLOCK.__init__()
    return CLOCK


def greeter(clock, window_min=10.0):  # clock: entries are stamped with CLOCK.at
    return Greeter(BrainConfig(greeting_window_min=window_min))


def decide_and_commit(g, message):
    decision = g.decide(message)
    g.commit(decision)
    return decision


# --- the rule ---------------------------------------------------------------------


def test_first_entry_is_greeted(clock):
    decision = greeter(clock).decide(entered())
    assert decision.decision == GREET and decision.say is not None
    assert decision.reason == "no greeting since start"
    assert decision.alternatives == [IGNORE]


def test_greeting_continues_the_flow_of_the_entry(clock):
    event = entered()
    say = greeter(clock).decide(event).say
    assert say.topic == SAY
    assert say.envelope.trace_id == event.envelope.trace_id
    assert say.envelope.causation_id == event.envelope.id
    assert say.envelope.source == "brain"
    assert (say.payload.lang, say.payload.priority) == ("es", "normal")


def test_two_entries_within_the_window_produce_one_greeting(clock):
    g = greeter(clock)
    assert decide_and_commit(g, entered("t1")).decision == GREET
    clock.advance(5)
    second = decide_and_commit(g, entered("t2"))
    assert second.decision == IGNORE and second.say is None
    assert second.reason == "greeted 5.0 s ago, within the window of 10 minutes"
    assert second.alternatives == [GREET]


def test_entry_after_the_window_is_greeted_again(clock):
    g = greeter(clock, window_min=10)
    decide_and_commit(g, entered())
    clock.advance(10 * 60)
    decision = g.decide(entered())
    assert decision.decision == GREET
    assert decision.reason == "no greeting in the last 10 minutes (last 600.0 s ago)"


def test_ignored_entries_do_not_extend_the_window(clock):
    g = greeter(clock, window_min=1)
    decide_and_commit(g, entered())
    clock.advance(50)
    decide_and_commit(g, entered())  # ignored
    clock.advance(10)
    assert g.decide(entered()).decision == GREET  # 60 s after the greeting


def test_uncommitted_greeting_does_not_start_the_window(clock):
    g = greeter(clock)
    g.decide(entered())  # publishing failed: no commit
    clock.advance(1)
    assert g.decide(entered()).decision == GREET


def test_window_uses_event_time_not_arrival_time(clock):
    """A replay shifts every ts by the same amount: decisions must not change."""
    g = greeter(clock, window_min=1)
    later = clock.at + timedelta(days=3)
    decide_and_commit(g, entered(at=later))
    assert g.decide(entered(at=later + timedelta(seconds=30))).decision == IGNORE
    assert g.decide(entered(at=later + timedelta(seconds=60))).decision == GREET


def test_out_of_order_event_counts_as_inside_the_window(clock):
    g = greeter(clock)
    decide_and_commit(g, entered())
    decision = g.decide(entered(at=clock.at - timedelta(seconds=5)))
    assert decision.decision == IGNORE and "0.0 s ago" in decision.reason


def test_zero_window_greets_every_entry(clock):
    g = greeter(clock, window_min=0)
    assert decide_and_commit(g, entered()).decision == GREET
    assert decide_and_commit(g, entered()).decision == GREET


# --- configuration ----------------------------------------------------------------


def test_config_accepts_fractional_and_integer_minutes():
    assert BrainConfig(greeting_window_min=0.05).greeting_window_min == 0.05
    assert BrainConfig.model_validate({"greeting_window_min": 10}).greeting_window_min == 10


@pytest.mark.parametrize(
    "config",
    [{"greeting_window_min": -1}, {"greeting_window_min": "10"}, {"lang": "fr"},
     {"greeting_text": ""}, {"greting_window_min": 10}],
)  # fmt: skip
def test_invalid_config_is_rejected(config):
    with pytest.raises(ValidationError):
        BrainConfig.model_validate(config)


# --- the service: publish and trace -------------------------------------------------


@pytest.fixture
def traces(tmp_path):
    return TraceWriter(tmp_path, "brain")


def all_traces(writer):
    return [t for path in sorted(writer.directory.glob("*.jsonl")) for t in read_traces(path)]


def test_each_decision_has_its_trace(clock, traces):
    service = FakeService()
    brain = Brain(service, greeter(clock), traces)
    first, second = entered("t1"), entered("t2", at=clock.at + timedelta(seconds=3))
    received = utc_now()
    brain.handle(first, received)
    brain.handle(second, utc_now())

    assert [m.topic for m in service.published] == [SAY]
    greet, ignore = all_traces(traces)
    say = service.published[0]
    assert (greet.kind, greet.name, greet.level, greet.component) == (
        "decision", "greet_on_entry", "L0", "brain",
    )  # fmt: skip
    assert greet.decision == GREET and greet.alternatives == [IGNORE]
    assert greet.trace_id == first.envelope.trace_id
    assert greet.ts == received
    assert greet.inputs.message_ids == [first.envelope.id]
    assert greet.outputs.message_ids == [say.envelope.id]
    assert greet.duration_ms >= 0 and greet.cost is None

    assert ignore.decision == IGNORE and ignore.reason.startswith("greeted 3.0 s ago")
    assert ignore.trace_id == second.envelope.trace_id
    assert ignore.inputs.message_ids == [second.envelope.id]
    assert ignore.outputs.message_ids == []


def test_failed_publish_is_traced_and_retried_on_next_entry(clock, traces):
    service = FakeService(fail=True)
    brain = Brain(service, greeter(clock), traces)
    event = entered()
    brain.handle(event, utc_now())
    decision, error = all_traces(traces)
    assert decision.decision == GREET and decision.outputs.message_ids == []
    assert error.kind == "error" and error.parent_span_id == decision.span_id
    assert error.trace_id == event.envelope.trace_id
    assert "no acknowledgement" in error.reason

    service.fail = False
    clock.advance(1)
    assert brain.handle(entered(), utc_now()).decision == GREET
    assert len(service.published) == 1


def test_traces_do_not_copy_message_content(clock, traces):
    Brain(FakeService(), greeter(clock), traces).handle(entered("secret-track"), utc_now())
    text = "".join(p.read_text() for p in traces.directory.glob("*.jsonl"))
    assert "secret-track" not in text and "Hola" not in text
