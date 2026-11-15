"""A throwaway Mosquitto on this machine, for the tests and `make sim`.

It runs the same pinned image as the Nano, so Docker and that image are needed; it
never pulls the image. MOSQUITTO=/path/to/mosquitto runs a native binary instead
(Ubuntu's AppArmor profile stops /usr/sbin/mosquitto from reading a config outside
/etc/mosquitto). It listens only on 127.0.0.1, on a free port.
"""

import os
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

from contracts.service import BusService
from deploy.broker.broker_config import BROKER_DIR_IN_IMAGE, MOSQUITTO_IMAGE, generate

PULL_HINT = f"docker pull {MOSQUITTO_IMAGE}"


def native_binary() -> str | None:
    return os.environ.get("MOSQUITTO") or None


def image_available() -> bool:
    """Never pulls: nothing here downloads by itself."""
    if not shutil.which("docker"):
        return False
    inspect = ["docker", "image", "inspect", MOSQUITTO_IMAGE]
    return subprocess.run(inspect, capture_output=True).returncode == 0


def broker_available() -> bool:
    return native_binary() is not None or image_available()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LocalBroker:
    """Generates a config in `directory` and starts the broker on a free port."""

    def __init__(self, directory: Path, environment: str, *, start_timeout_s: float = 15):
        self.directory = directory
        self.port = free_port()
        self.container: str | None = None
        listeners = [f"127.0.0.1:{self.port}"]
        mosquitto = native_binary()
        if mosquitto:
            self.passwords = generate(directory, environment, listeners)
            command = [mosquitto, "-c", str(directory / "mosquitto.conf")]
        else:
            self.passwords = generate(
                directory, environment, listeners, broker_dir=BROKER_DIR_IN_IMAGE
            )
            self.container = f"sancho-local-broker-{uuid.uuid4().hex[:8]}"
            command = [
                "docker", "run", "--rm", "--name", self.container, "--network", "host",
                "--user", f"{os.getuid()}:{os.getgid()}",
                "-v", f"{directory}:{BROKER_DIR_IN_IMAGE}:ro",
                MOSQUITTO_IMAGE, "mosquitto", "-c", f"{BROKER_DIR_IN_IMAGE}/mosquitto.conf",
            ]  # fmt: skip
        self.log = directory.parent / f"{directory.name}-broker.log"
        with self.log.open("w") as log:
            self.process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + start_timeout_s
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"mosquitto exited:\n{self.log.read_text()}")
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.05)
        self.stop()
        raise RuntimeError("mosquitto did not start")

    def credential_file(self, role: str) -> Path:
        return self.directory / "credentials" / role

    def service(self, role: str, **kwargs) -> BusService:
        return BusService(role, self.passwords[role], port=self.port, **kwargs)

    def stop(self) -> None:
        if self.container:
            subprocess.run(["docker", "rm", "-f", self.container], capture_output=True)
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(5)

    def __enter__(self) -> "LocalBroker":
        return self

    def __exit__(self, *exc) -> None:
        self.stop()
