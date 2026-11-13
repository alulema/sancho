"""T2 probe: reads CSI camera frames through a gst-launch subprocess.

The interpreter needs no GStreamer bindings, so this works with any Python that has
numpy. Frames stay in memory and are discarded; nothing is written to disk.

Kept compatible with Python 3.6 so the same probe runs on the system Python as a
baseline.
"""

import argparse
import json
import os
import platform
import resource
import subprocess
import sys
import time

import numpy as np


def build_pipeline(width, height, fps, frames, fd):
    return [
        "gst-launch-1.0",
        "-q",
        "nvarguscamerasrc",
        f"num-buffers={frames}",
        "!",
        f"video/x-raw(memory:NVMM),width=1280,height=720,framerate={fps}/1",
        "!",
        "nvvidconv",
        "!",
        f"video/x-raw,width={width},height={height},format=BGRx",
        "!",
        "fdsink",
        f"fd={fd}",
    ]


def read_exact(stream, view):
    filled = 0
    while filled < len(view):
        n = stream.readinto(view[filled:])
        if not n:
            return False
        filled += n
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--warmup", type=float, default=2.0)
    args = parser.parse_args()

    frames = int(args.fps * (args.seconds + args.warmup))
    frame_size = args.width * args.height * 4
    read_fd, write_fd = os.pipe()
    proc = subprocess.Popen(
        build_pipeline(args.width, args.height, args.fps, frames, write_fd),
        pass_fds=(write_fd,),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.close(write_fd)

    buf = bytearray(frame_size)
    view = memoryview(buf)
    arrivals = []
    brightness = []
    with os.fdopen(read_fd, "rb", buffering=0) as stream:
        while read_exact(stream, view):
            arrivals.append(time.monotonic())
            bgr = np.frombuffer(buf, dtype=np.uint8).reshape(args.height, args.width, 4)
            bgr = np.ascontiguousarray(bgr[:, :, :3])
            brightness.append(float(bgr.mean()))
    proc.wait()

    measured = [t for t in arrivals if t - arrivals[0] >= args.warmup] if arrivals else []
    fps = (len(measured) - 1) / (measured[-1] - measured[0]) if len(measured) > 1 else 0.0
    self_usage = resource.getrusage(resource.RUSAGE_SELF)
    child_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    result = {
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "machine": platform.machine(),
        "resolution": f"{args.width}x{args.height}",
        "requested_fps": args.fps,
        "frames_read": len(arrivals),
        "frames_expected": frames,
        "measured_fps": round(fps, 2),
        "brightness_min": round(min(brightness), 1) if brightness else None,
        "brightness_max": round(max(brightness), 1) if brightness else None,
        "python_cpu_s": round(self_usage.ru_utime + self_usage.ru_stime, 2),
        "gstreamer_cpu_s": round(child_usage.ru_utime + child_usage.ru_stime, 2),
        "wall_s": round(arrivals[-1] - arrivals[0], 2) if arrivals else 0.0,
        "gst_exit": proc.returncode,
    }
    print(json.dumps(result))
    return 0 if result["frames_read"] == frames and proc.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
