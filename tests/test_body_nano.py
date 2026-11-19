"""T6 on the Nano: real camera, real detector, real voice. Excluded by default.

    .venv/bin/pytest -m nano tests/test_body_nano.py

Needs the CSI camera and the models from deploy/nano/fetch_models.py. Nothing is
played or saved: frames and audio stay in memory.
"""

import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.nano
MODELS = Path.home() / "sancho" / "models"
ROOT = Path(__file__).resolve().parent.parent


def test_camera_delivers_frames_at_the_requested_rate():
    from body.camera import FRAME_H, FRAME_W, Camera, gst_command

    with Camera(lambda fd: gst_command(fd, fps=10)) as camera:
        first = camera.next_frame(0, timeout_s=15)  # Argus takes a few seconds to start
        assert first is not None and len(first.data) == FRAME_W * FRAME_H * 4
        time.sleep(3)
        last = camera.next_frame(first.seq, timeout_s=2)
    rate = (last.seq - first.seq) / (last.t - first.t)
    assert 8 <= rate <= 12


def test_detector_runs_on_a_camera_frame():
    from body.camera import Camera, gst_command
    from body.detector import PersonDetector

    detector = PersonDetector(str(MODELS / "nanodet-plus-416.onnx"))
    with Camera(lambda fd: gst_command(fd, fps=10)) as camera:
        frame = camera.next_frame(0, timeout_s=15)
    detector.detect(frame.data)  # warm-up
    started = time.perf_counter()
    people = detector.detect(frame.data)
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert elapsed_ms < 1000
    for score, x, y, w, h in people:  # whatever is in the studio, the format holds
        assert 0 <= score <= 1 and all(0 <= v <= 1 for v in (x, y, w, h))


def test_the_voice_worker_synthesizes_spanish():
    from body.speech import TtsWorker, worker_command

    worker = TtsWorker(worker_command(str(MODELS / "es_ES-davefx-medium.onnx")), cwd=str(ROOT))
    worker.start()
    audio = b"".join(worker.synthesize("t1", "Hola."))
    worker.close()
    assert worker.sample_rate == 22050
    assert len(audio) / 2 / worker.sample_rate > 0.3  # some real speech, not silence


def test_the_worker_is_the_only_module_that_imports_piper():
    importers = [p.name for p in (ROOT / "body").glob("*.py") if "import piper" in p.read_text()
                 or "from piper" in p.read_text()]  # fmt: skip
    assert importers == ["tts_worker.py"]
    assert "piper" not in sys.modules
