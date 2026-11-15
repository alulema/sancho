"""What every component's entry point shares: bus arguments, password file, signals."""

import argparse
import logging
import signal
import threading
from pathlib import Path

DEFAULT_TRACES = Path("traces")


def add_bus_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--password-file",
        type=Path,
        required=True,
        help="file with this role's bus password (credentials/<role> from broker_config)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--traces", type=Path, default=DEFAULT_TRACES, help="trace directory")


def read_password(path: Path) -> str:
    password = path.read_text(encoding="utf-8").strip()
    if not password:
        raise SystemExit(f"empty password file: {path}")
    return password


def stop_on_signals() -> threading.Event:
    """An event set by SIGTERM or SIGINT, so the component can close cleanly."""
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    return stop


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
