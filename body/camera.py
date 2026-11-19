"""CSI camera through a `gst-launch-1.0` subprocess (T6, ADR-0012).

A reader thread drains the pipe and keeps only the newest frame, so the detector
always works on a recent one, however slow it is. Frames live only in memory: nothing
is written to disk or published (CLAUDE.md).

The pipe gives no capture timestamps; each frame is stamped when it arrives, which is
later than its capture by the ISP, the scaling and the pipe (see the T6 log).
"""

import logging
import os
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from contracts.types import utc_now

FRAME_W, FRAME_H = 416, 234  # the detector's input width, 16:9 (body/detector.py)
log = logging.getLogger("sancho.body.camera")


def gst_command(fd: int, *, fps: int = 10, flip: int = 2) -> list[str]:
    """The camera at 1280x720, scaled by the hardware to the detector's 416x234 BGRx.

    flip-method=2 rotates 180°: the camera is mounted upside down (T2 log).
    """
    return [
        "gst-launch-1.0", "-q", "nvarguscamerasrc", "!",
        "video/x-raw(memory:NVMM),width=1280,height=720,framerate=30/1", "!",
        "nvvidconv", f"flip-method={flip}", "!",
        f"video/x-raw,width={FRAME_W},height={FRAME_H},format=BGRx", "!",
        "videorate", "drop-only=true", "!", f"video/x-raw,framerate={fps}/1", "!",
        "fdsink", f"fd={fd}",
    ]  # fmt: skip


@dataclass
class Frame:
    seq: int
    t: float  # monotonic seconds at arrival
    ts: datetime  # UTC at arrival
    data: bytes  # FRAME_W * FRAME_H * 4 bytes, BGRx


class Camera:
    def __init__(self, command: Callable[[int], list[str]] = gst_command, *,
                 frame_size: int = FRAME_W * FRAME_H * 4, restart_s: float = 2.0):  # fmt: skip
        self._command = command
        self._size = frame_size
        self._restart_s = restart_s
        self._latest: Frame | None = None
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._process: subprocess.Popen | None = None
        self._thread = threading.Thread(target=self._run, name="camera", daemon=True)
        self.restarts = 0

    def start(self) -> "Camera":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        process = self._process
        if process and process.poll() is None:
            process.terminate()
        self._thread.join(timeout=5)
        with self._cond:
            self._cond.notify_all()

    def __enter__(self) -> "Camera":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    def next_frame(self, after: int, timeout_s: float = 5.0) -> Frame | None:
        """The newest frame with a sequence number above `after`, or None on timeout
        or stop. Frames the caller was too slow to take are dropped."""
        with self._cond:
            ok = self._cond.wait_for(
                lambda: self._stop.is_set() or (self._latest and self._latest.seq > after),
                timeout_s,
            )
            if not ok or self._stop.is_set() or self._latest is None:
                return None
            return self._latest

    # --- reader thread -----------------------------------------------------------

    def _run(self) -> None:
        seq = 0
        while not self._stop.is_set():
            read, write = os.pipe()
            try:
                self._process = subprocess.Popen(self._command(write), pass_fds=(write,),
                                                 stdout=subprocess.DEVNULL,
                                                 stderr=subprocess.PIPE)  # fmt: skip
            except OSError as error:
                os.close(read)
                os.close(write)
                log.error("cannot start the camera pipeline: %s", error)
                self._stop.wait(self._restart_s)
                continue
            os.close(write)
            with os.fdopen(read, "rb", buffering=0) as stream:
                seq = self._read_frames(stream, seq)
            process = self._process
            try:
                process.terminate()
                _, err = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                _, err = process.communicate()
            if self._stop.is_set():
                return
            self.restarts += 1
            tail = (err or b"").decode(errors="replace").strip().splitlines()[-3:]
            log.error("camera pipeline ended (code %s): %s; restarting in %.0f s",
                      process.returncode, " | ".join(tail) or "no output",
                      self._restart_s)  # fmt: skip
            self._stop.wait(self._restart_s)

    def _read_frames(self, stream, seq: int) -> int:
        buffer = bytearray(self._size)
        while not self._stop.is_set():
            view, got = memoryview(buffer), 0
            while got < self._size:
                n = stream.readinto(view[got:])
                if not n:
                    return seq
                got += n
            seq += 1
            frame = Frame(seq, time.monotonic(), utc_now(), bytes(buffer))
            with self._cond:
                self._latest = frame
                self._cond.notify_all()
        return seq
