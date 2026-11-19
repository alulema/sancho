"""T6: the body agent's logic without hardware (presence, decoding, voice, camera)."""

import io
import sys
import textwrap
import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path

import pytest

from body.presence import Detection, Entered, Left, Presence
from body.ttsproto import AUDIO, END, ProtocolError, read_frame, write_frame
from contracts.bus import decode, encode, make_message
from contracts.topics import Say
from contracts.traces import TraceWriter, read_traces
from contracts.types import utc_now

ROOT = Path(__file__).resolve().parent.parent
T0 = utc_now()
PERSON = [Detection(0.8, (0.4, 0.1, 0.2, 0.8))]


def at(presence, t, detections=PERSON):
    return presence.update(t, T0 + timedelta(seconds=t), detections)


# --- presence and hysteresis ---------------------------------------------------------


def test_one_entry_after_the_hysteresis_and_one_exit_after_the_absence():
    p = Presence(enter_ms=500, min_hits=2, leave_ms=3000, new_track_id=lambda: "t1")
    events = [at(p, t / 10) for t in range(0, 30)]  # 3 s present at 10 fps
    entered = [e for e in events if e]
    assert len(entered) == 1 and isinstance(entered[0], Entered)
    assert entered[0].first_seen_ts == T0 and entered[0].frame_ts == T0 + timedelta(seconds=0.5)
    assert at(p, 5.8, []) is None  # 2.9 s without anyone: still present
    left = at(p, 5.9, [])
    assert left == Left("t1", 2.9)  # from the first to the last detection


def test_short_gaps_while_walking_do_not_end_the_visit():
    p = Presence(leave_ms=3000)
    seen = [at(p, t) for t in (0, 0.25, 0.5, 0.75)]
    assert sum(isinstance(e, Entered) for e in seen) == 1
    assert at(p, 2.0, []) is None and at(p, 2.25) is None  # 1.5 s gap, like the walk test
    assert p.present


def test_a_single_flicker_is_not_an_entry():
    p = Presence(enter_ms=500, min_hits=2, max_gap_ms=1000)
    assert at(p, 0) is None
    assert at(p, 1.2, []) is None and not p.present  # the candidate expired
    assert at(p, 1.3) is None  # starts over: one hit only
    assert at(p, 1.9) is not None


def test_min_hits_and_enter_time_are_both_needed():
    p = Presence(enter_ms=500, min_hits=3)
    assert [at(p, t) for t in (0, 0.6)] == [None, None]  # 0.6 s but only two frames
    assert isinstance(at(p, 0.7), Entered)


def test_the_best_detection_of_the_confirming_frame_is_reported():
    p = Presence(enter_ms=0, min_hits=1)
    weak, strong = Detection(0.4, (0, 0, 0.1, 0.1)), Detection(0.9, (0.5, 0.5, 0.2, 0.2))
    assert at(p, 0, [weak, strong]).detection == strong


def test_close_ends_an_open_visit():
    p = Presence(enter_ms=0, min_hits=1, new_track_id=lambda: "t9")
    at(p, 0)
    at(p, 1)
    assert p.close() == Left("t9", 1.0) and p.close() is None


# --- TTS protocol, worker and speaker -------------------------------------------------


def test_frames_round_trip_and_bad_frames_are_rejected():
    stream = io.BytesIO()
    write_frame(stream, AUDIO, b"\x01\x02")
    write_frame(stream, END, b"{}")
    stream.seek(0)
    assert read_frame(stream) == (AUDIO, b"\x01\x02")
    assert read_frame(stream) == (END, b"{}")
    assert read_frame(stream) is None
    with pytest.raises(ProtocolError):
        read_frame(io.BytesIO(b"Z\x00\x00\x00\x01x"))
    with pytest.raises(ProtocolError):
        read_frame(io.BytesIO(b"A\x00\x00\x00\x05ab"))  # cut inside the frame


FAKE_WORKER = textwrap.dedent("""
    import json, sys
    from body.ttsproto import AUDIO, END, ERROR, READY, write_frame, write_json
    out = sys.stdout.buffer
    write_json(out, READY, {"sample_rate": 16000})
    for line in sys.stdin:
        item = json.loads(line)
        if item["text"] == "die":
            sys.exit(3)
        if item["text"] == "fail":
            write_json(out, ERROR, {"id": item["id"], "error": "no voice for that"})
            continue
        for _ in range(3):
            write_frame(out, AUDIO, b"\\x00\\x00" * 160)
        write_json(out, END, {"id": item["id"]})
""")


class Published:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)

    def states(self):
        return [m.payload.state for m in self.messages]


def say(text="Hola"):
    payload = Say(say_id=uuid.uuid4(), text=text, lang="es", priority="normal")
    return make_message("sancho/body/speech/cmd/say", "brain", payload)


def speaker_with(tmp_path, player_code="import sys; sys.stdin.buffer.read()"):
    from body.speech import Speaker, TtsWorker

    worker = TtsWorker([sys.executable, "-c", FAKE_WORKER], cwd=str(ROOT))
    bus = Published()
    speaker = Speaker(bus, TraceWriter(tmp_path, "body"), worker,
                      lambda rate: [sys.executable, "-c", player_code])  # fmt: skip
    return speaker, worker, bus


def test_speaker_publishes_started_then_finished_and_traces_it(tmp_path):
    speaker, worker, bus = speaker_with(tmp_path)
    worker.start()
    command = say()
    assert speaker.speak(command, utc_now()) == "finished"
    assert bus.states() == ["started", "finished"]
    for status in bus.messages:
        assert status.envelope.causation_id == command.envelope.id
        assert status.envelope.trace_id == command.envelope.trace_id
        decode(status.topic, encode(status))  # valid on the wire
    (trace,) = read_traces(next(tmp_path.glob("body-*.jsonl")))
    assert trace.kind == "action" and trace.name == "speak"
    assert trace.outputs.message_ids == [m.envelope.id for m in bus.messages]
    worker.close()


def test_synthesis_error_is_published_and_the_worker_keeps_serving(tmp_path):
    speaker, worker, bus = speaker_with(tmp_path)
    assert speaker.speak(say("fail"), utc_now()) == "error"  # also starts the worker
    assert bus.states() == ["error"] and bus.messages[0].payload.error == "no voice for that"
    assert speaker.speak(say(), utc_now()) == "finished" and worker.starts == 1
    worker.close()


def test_a_dead_worker_is_an_error_and_is_restarted_next_time(tmp_path):
    speaker, worker, bus = speaker_with(tmp_path)
    assert speaker.speak(say("die"), utc_now()) == "error"
    assert "exited" in bus.messages[0].payload.error
    assert speaker.speak(say(), utc_now()) == "finished" and worker.starts == 2
    worker.close()


def test_a_failing_player_is_an_error_after_started(tmp_path):
    failing = "import sys; sys.stdin.buffer.read(); sys.exit(2)"
    speaker, worker, bus = speaker_with(tmp_path, failing)
    assert speaker.speak(say(), utc_now()) == "error"
    assert bus.states() == ["started", "error"]
    worker.close()


def test_worker_that_cannot_load_reports_why():
    from body.speech import TtsError, TtsWorker

    code = (
        "import sys; from body.ttsproto import ERROR, write_json; "
        "write_json(sys.stdout.buffer, ERROR, {'id': None, 'error': 'no such voice'})"
    )
    worker = TtsWorker([sys.executable, "-c", code], cwd=str(ROOT))
    with pytest.raises(TtsError, match="no such voice"):
        worker.start()


# --- camera -----------------------------------------------------------------------


def fake_gst(frames: int, size: int, delay: float = 0.0):
    code = (f"import os,sys,time\nfd=int(sys.argv[1])\nfor i in range({frames}):\n"
            f"    os.write(fd, bytes([i % 256]) * {size}); time.sleep({delay})\n")  # fmt: skip
    return lambda fd: [sys.executable, "-c", code, str(fd)]


def test_camera_hands_out_the_newest_frame_and_drops_the_rest():
    from body.camera import Camera

    with Camera(fake_gst(20, 64, 0.01), frame_size=64, restart_s=60) as camera:
        time.sleep(0.6)  # all 20 frames arrive while nobody reads
        frame = camera.next_frame(0, timeout_s=2)
        assert frame.seq == 20 and frame.data == bytes([19]) * 64
        assert camera.next_frame(frame.seq, timeout_s=0.2) is None  # nothing newer


def test_camera_restarts_a_pipeline_that_dies():
    from body.camera import Camera

    with Camera(fake_gst(2, 16), frame_size=16, restart_s=0.05) as camera:
        deadline = time.monotonic() + 3
        while camera.restarts < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert camera.restarts >= 2
        frame = camera.next_frame(0, timeout_s=2)
        assert frame is not None and frame.seq >= 3  # sequence keeps growing across restarts


# --- vision loop ----------------------------------------------------------------------


class ScriptedCamera:
    def __init__(self, frames):
        self.frames = list(frames)  # (t, people)

    def next_frame(self, after, timeout_s):
        from body.camera import Frame

        if not self.frames:
            time.sleep(0.01)
            return None
        t, people = self.frames.pop(0)
        return Frame(after + 1, t, T0 + timedelta(seconds=t), people)


class PassThrough:
    def detect(self, people):
        return people


def test_vision_publishes_valid_entry_and_exit_messages():
    from body.service import Vision

    person = [(0.77, 0.4, 0.1, 0.2, 0.8)]
    frames = [(t / 4, person) for t in range(8)] + [(2 + t, []) for t in range(5)]
    bus = Published()
    stop = threading.Event()
    vision = Vision(bus, ScriptedCamera(frames), PassThrough(),
                    Presence(enter_ms=500, leave_ms=3000, new_track_id=lambda: "t1"))  # fmt: skip
    thread = threading.Thread(target=vision.run, args=(stop,))
    thread.start()
    time.sleep(0.3)
    stop.set()
    thread.join(5)
    entered, left = bus.messages
    decode(entered.topic, encode(entered))
    p = entered.payload
    assert (p.track_id, p.confidence, p.bbox) == ("t1", 0.77, [0.4, 0.1, 0.2, 0.8])
    assert p.first_seen_ts <= p.frame_ts <= entered.envelope.ts
    assert left.topic.endswith("person_left") and left.payload.duration_s == 1.75


def test_fetch_models_pins_every_file_the_body_loads():
    from body.service import DETECTOR_MODEL, VOICE_MODEL
    from deploy.nano.fetch_models import MODELS

    assert {name for name, _, _ in MODELS} == {DETECTOR_MODEL, VOICE_MODEL, VOICE_MODEL + ".json"}
    assert all(len(digest) == 64 and url.startswith("https://") for _, url, digest in MODELS)


def test_paused_time_is_not_absence():
    p = Presence(enter_ms=0, min_hits=1, leave_ms=3000, new_track_id=lambda: "t1")
    at(p, 0)
    p.pause(8.0)  # spoke for 8 s without looking
    assert at(p, 9.0, []) is None and p.present  # only 1 s of real absence
    assert at(p, 11.0, []) == Left("t1", 8.0)  # the visit spans the pause


class CountingDetector(PassThrough):
    def __init__(self):
        self.calls = 0

    def detect(self, people):
        self.calls += 1
        return people


def test_vision_does_not_detect_while_the_body_speaks():
    from body.service import Vision

    speaking = threading.Event()
    speaking.set()
    detector = CountingDetector()
    frames = [(t / 10, [(0.8, 0.4, 0.1, 0.2, 0.8)]) for t in range(50)]
    vision = Vision(Published(), ScriptedCamera(frames), detector, Presence(),
                    paused=speaking.is_set)  # fmt: skip
    stop = threading.Event()
    thread = threading.Thread(target=vision.run, args=(stop,))
    thread.start()
    time.sleep(0.2)
    assert detector.calls == 0
    speaking.clear()
    time.sleep(0.2)
    stop.set()
    thread.join(5)
    assert detector.calls > 0 and vision.paused_s >= 0.15
