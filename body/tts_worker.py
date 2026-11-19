# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file imports Piper (piper-tts, GPL-3.0-or-later) and is therefore distributed
# under the GPL-3.0-or-later. It is the only file in the repository that does: the rest
# of the body talks to it through pipes (body/ttsproto.py), as ADR-0018 decides.
"""TTS worker: loads a Piper voice once and synthesizes requests from stdin.

    python -m body.tts_worker --model VOICE.onnx

Speaks the protocol of body/ttsproto.py. Audio only goes to stdout, never to disk.
"""

import argparse
import json
import sys

from body.ttsproto import AUDIO, END, ERROR, READY, write_frame, write_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m body.tts_worker")
    parser.add_argument("--model", required=True, help="Piper voice (.onnx, with .onnx.json)")
    args = parser.parse_args(argv)
    out = sys.stdout.buffer
    try:
        from piper import PiperVoice

        voice = PiperVoice.load(args.model)
    except Exception as error:  # report it through the protocol, then exit
        write_json(out, ERROR, {"id": None, "error": f"cannot load {args.model}: {error}"})
        return 1
    write_json(out, READY, {"sample_rate": voice.config.sample_rate})
    for line in sys.stdin:
        if not line.strip():
            continue
        request_id = None
        try:
            item = json.loads(line)
            request_id, text = str(item["id"]), str(item["text"])
            for chunk in voice.synthesize(text):
                write_frame(out, AUDIO, chunk.audio_int16_bytes)
            write_json(out, END, {"id": request_id})
        except Exception as error:
            write_json(out, ERROR, {"id": request_id, "error": str(error)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
