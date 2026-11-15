"""T8: camera scripts, the simulated speaker, and the full chain on this machine."""

import threading
import uuid

import pytest
import yaml

from brain.greeter import GREET, IGNORE
from contracts.bus import decode, encode, make_message
from contracts.topics import Say
from contracts.traces import TraceWriter, read_traces
from contracts.types import utc_now
from deploy.broker.local import PULL_HINT, broker_available
from sim.body import ENTERED, LEFT, SAY, STATUS, Camera, Speaker
from sim.run import DEFAULT_SCRIPT, simulate
from sim.script import InvalidScript, Script, load_script

needs_broker = pytest.mark.skipif(
    not broker_available(), reason=f"no broker: run `{PULL_HINT}` or set MOSQUITTO"
)


class FakeService:
    def __init__(self):
        self.published = []

    def publish(self, message):
        self.published.append(decode(message.topic, encode(message)))


def write_script(tmp_path, steps, description="test"):
    path = tmp_path / "script.yaml"
    path.write_text(yaml.safe_dump({"description": description, "steps": steps}))
    return path


# --- scripts ----------------------------------------------------------------------


def test_default_script_is_valid():
    script = load_script(DEFAULT_SCRIPT)
    assert [s.enter.track_id for s in script.steps if s.enter] == ["t1", "t2"]
    assert script.duration_ms == 8000


@pytest.mark.parametrize(
    ("steps", "error"),
    [
        ([{"at_ms": 0, "leave": {"track_id": "t1"}}], "leaves without having entered"),
        ([{"at_ms": 0, "enter": {"track_id": "t1"}}, {"at_ms": 1, "enter": {"track_id": "t1"}}],
         "enters twice"),
        ([{"at_ms": 5, "enter": {"track_id": "t1"}}, {"at_ms": 1, "leave": {"track_id": "t1"}}],
         "ordered"),
        ([{"at_ms": 0, "enter": {"track_id": "t1"}, "leave": {"track_id": "t1"}}],
         "exactly one"),
        ([{"at_ms": 0}], "exactly one"),
        ([{"at_ms": 0, "enter": {"track_id": "t1", "confidence": 1.5}}], "less than or equal"),
        ([{"at_ms": 0, "enter": {"track_id": "t1", "colour": "red"}}], "Extra inputs"),
        ([], "at least 1"),
    ],
)  # fmt: skip
def test_invalid_scripts_are_rejected(tmp_path, steps, error):
    with pytest.raises(InvalidScript, match=error):
        load_script(write_script(tmp_path, steps))


def test_broken_yaml_is_rejected(tmp_path):
    path = tmp_path / "broken.yaml"
    path.write_text("steps: [")
    with pytest.raises(InvalidScript):
        load_script(path)


# --- camera -----------------------------------------------------------------------


def test_camera_publishes_the_script_with_latency_marks():
    script = Script.model_validate(
        {"description": "x", "steps": [
            {"at_ms": 0, "enter": {"track_id": "t1", "hysteresis_ms": 250}},
            {"at_ms": 50, "leave": {"track_id": "t1"}},
        ]}
    )  # fmt: skip
    service = FakeService()
    Camera(service, script).play(threading.Event())
    entered, left = service.published
    assert (entered.topic, left.topic) == (ENTERED, LEFT)
    assert entered.envelope.source == "sim"
    p = entered.payload
    assert p.first_seen_ts <= p.frame_ts <= entered.envelope.ts
    assert (p.frame_ts - p.first_seen_ts).total_seconds() == 0.25
    assert left.payload.track_id == "t1" and 0.04 <= left.payload.duration_s < 1


def test_camera_stops_when_asked():
    script = Script.model_validate(
        {"description": "x", "steps": [{"at_ms": 60_000, "enter": {"track_id": "t1"}}]}
    )
    stop = threading.Event()
    stop.set()
    service = FakeService()
    Camera(service, script).play(stop)
    assert service.published == []


# --- speaker ----------------------------------------------------------------------


def say_message():
    payload = Say(say_id=uuid.uuid4(), text="Hola", lang="es", priority="normal")
    return make_message(SAY, "brain", payload)


def test_speaker_reports_started_then_finished_and_traces(tmp_path):
    service, slept = FakeService(), []
    writer = TraceWriter(tmp_path, "sim")
    speaker = Speaker(service, writer, synth_ms=200, speech_ms=1500, sleep=slept.append)
    say, received = say_message(), utc_now()
    speaker.speak(say, received)

    assert slept == [0.2, 1.5]
    started, finished = service.published
    assert [m.payload.state for m in service.published] == ["started", "finished"]
    for status in (started, finished):
        assert status.topic == STATUS
        assert status.payload.say_id == say.payload.say_id
        assert status.envelope.trace_id == say.envelope.trace_id
        assert status.envelope.causation_id == say.envelope.id
    (trace,) = read_traces(next(tmp_path.glob("sim-*.jsonl")))
    assert (trace.kind, trace.name, trace.component) == ("action", "speak", "sim")
    assert trace.ts == received
    assert trace.inputs.message_ids == [say.envelope.id]
    assert trace.outputs.message_ids == [started.envelope.id, finished.envelope.id]


# --- the whole chain --------------------------------------------------------------


@needs_broker
def test_chain_two_entries_within_the_window(tmp_path):
    result = simulate(DEFAULT_SCRIPT, tmp_path, synth_ms=50, speech_ms=200, linger_ms=500,
                      quiet=True)  # fmt: skip
    assert result.exit_codes == {"brain": 0, "sim": 0}
    assert len(result.on(ENTERED)) == 2
    (say,) = result.on(SAY)
    states = [m.payload.state for m in result.on(STATUS)]
    assert states == ["started", "finished"]
    first = result.on(ENTERED)[0]
    assert say.envelope.trace_id == first.envelope.trace_id
    assert [d.decision for d in result.decisions] == [GREET, IGNORE]
    assert [a.name for a in result.actions] == ["speak"]
    # Both services announced themselves and closed cleanly (no last will).
    health = [m for m in result.messages if m.topic.startswith("sancho/sys/")]
    assert {(m.topic, m.payload.status) for m in health} == {
        ("sancho/sys/brain/health", "online"), ("sancho/sys/brain/health", "offline"),
        ("sancho/sys/body/health", "online"), ("sancho/sys/body/health", "offline"),
    }  # fmt: skip
    assert not any(m.payload.last_will for m in health)
    assert (result.run_dir / "brain.log").exists() and (result.run_dir / "sim.log").exists()


@needs_broker
def test_chain_greets_again_after_the_window(tmp_path):
    script = write_script(tmp_path, [
        {"at_ms": 0, "enter": {"track_id": "t1"}},
        {"at_ms": 300, "leave": {"track_id": "t1"}},
        {"at_ms": 1600, "enter": {"track_id": "t2"}},
    ])  # fmt: skip
    result = simulate(script, tmp_path / "out", greeting_window_min=0.02, synth_ms=50,
                      speech_ms=100, linger_ms=500, quiet=True)  # fmt: skip
    assert result.ok
    assert len(result.on(SAY)) == 2
    assert [d.decision for d in result.decisions] == [GREET, GREET]
