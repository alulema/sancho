"""Downloads the body's models to ~/sancho/models and checks their SHA-256 (T6).

    python3 deploy/nano/fetch_models.py [--dest ~/sancho/models]

Development setup, run once by hand: the body never downloads anything at runtime.
Each file must match its pinned checksum, or it is deleted and the script fails. Only
the standard library, so it runs with any Python 3.6+.

Models (ADR-0017, ADR-0018):
- NanoDet-Plus 416 (person detection), opencv_zoo, Apache-2.0.
- Piper voice es_ES-davefx-medium, rhasspy/piper-voices, dataset CC0.
"""

import argparse
import hashlib
import os
import sys
import urllib.request

ZOO = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
VOICES = "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/"
MODELS = [
    ("nanodet-plus-416.onnx",
     ZOO + "object_detection_nanodet/object_detection_nanodet_2022nov.onnx",
     "4b82da9944b88577175ee23a459dce2e26e6e4be573def65b1055dc2d9720186"),
    ("es_ES-davefx-medium.onnx", VOICES + "es_ES-davefx-medium.onnx",
     "d2c9224e122321aac3c33343957fff4d0f465226cb74c66b0f520ca3f8c0dd07"),
    ("es_ES-davefx-medium.onnx.json", VOICES + "es_ES-davefx-medium.onnx.json",
     "7d82d069eccca0f87963bd23c33166fe1ef6d24a6b231543931bfe692397f256"),
]  # fmt: skip


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dest", default=os.path.expanduser("~/sancho/models"))
    args = parser.parse_args()
    os.makedirs(args.dest, exist_ok=True)
    failed = False
    for name, url, expected in MODELS:
        path = os.path.join(args.dest, name)
        if os.path.exists(path) and sha256(path) == expected:
            print("ok        " + name)
            continue
        partial = path + ".partial"
        print("download  " + name)
        try:
            urllib.request.urlretrieve(url, partial)
        except OSError as error:
            print(f"ERROR     {name}: {error}", file=sys.stderr)
            failed = True
            continue
        actual = sha256(partial)
        if actual != expected:
            os.remove(partial)
            print(f"ERROR     {name}: sha256 {actual} instead of {expected}", file=sys.stderr)
            failed = True
            continue
        os.replace(partial, path)
        print("ok        " + name)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
