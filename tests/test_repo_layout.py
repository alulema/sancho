import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def protected_paths() -> list[str]:
    lines = (ROOT / "PROTECTED_PATHS").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def is_git_ignored(path: str) -> bool:
    result = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False)
    return result.returncode == 0


@pytest.mark.parametrize(
    "path",
    [
        "CLAUDE.md",
        "PROTECTED_PATHS",
        "README.md",
        "Makefile",
        "docs/diseno.md",
        "docs/specs",
        "docs/contratos",
        "docs/adr",
        "docs/bitacora",
        "contracts",
        "body",
        "brain",
        "sim",
        "eval",
        "deploy",
    ],
)
def test_expected_path_exists(path: str) -> None:
    assert (ROOT / path).exists()


def test_protected_paths_protects_itself_and_the_bench() -> None:
    entries = protected_paths()
    assert "PROTECTED_PATHS" in entries
    assert "eval/" in entries


def test_protected_paths_entries_exist() -> None:
    for entry in protected_paths():
        assert (ROOT / entry).exists(), entry


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "secrets/mqtt.txt",
        "deploy/mosquitto/passwd",
        "deploy/node.key",
        "deploy/node.pem",
        "models/face.onnx",
        "body/face.caffemodel",
        "recordings/session.jsonl",
        "traces/brain.jsonl",
        "body/clip.wav",
        "sim/clip.mp4",
    ],
)
def test_sensitive_files_are_ignored(path: str) -> None:
    assert is_git_ignored(path)


@pytest.mark.parametrize(
    "path",
    [
        ".env.example",
        "eval/results/2026-11-05.json",
        "eval/cases/e0-greet.yaml",
        "docs/bitacora/2026-11-05-latencia.md",
        "uv.lock",
    ],
)
def test_versioned_files_are_not_ignored(path: str) -> None:
    assert not is_git_ignored(path)
