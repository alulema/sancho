"""ACL data against the contract table, and the generated broker files (T4)."""

import re
import stat

import pytest

from contracts.acl import ROLES, may_publish, roles_for, topic_matches
from deploy.broker.broker_config import acl_text, conf_text, generate, hash_password
from tests.contract_docs import CONTRACTS_DIR

ENVIRONMENTS = {"producción y pruebas": ("prod", "test"), "solo pruebas": ("test",)}


def contract_acl_rows() -> dict[str, list[str]]:
    text = (CONTRACTS_DIR / "topicos-e0.md").read_text(encoding="utf-8")
    section = text.split("## ACL de E0", 1)[1].split("\n\n", 2)[1]
    rows = {}
    for line in section.splitlines()[2:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows[cells[0]] = cells[1:]
    return rows


def parse_patterns(cell: str, rows: dict, column: int) -> tuple[str, ...]:
    if cell == "nada":
        return ()
    if same := re.fullmatch(r"lo mismo que (\w+)", cell):
        return parse_patterns(rows[same.group(1)][column], rows, column)
    return tuple(re.findall(r"`([^`]+)`", cell))


def test_roles_match_the_contract_table():
    rows = contract_acl_rows()
    assert set(rows) == set(ROLES)
    for name, (environment, publish, subscribe) in rows.items():
        role = ROLES[name]
        assert role.environments == ENVIRONMENTS[environment], name
        assert role.publish == parse_patterns(publish, rows, 1), name
        assert role.subscribe == parse_patterns(subscribe, rows, 2), name


@pytest.mark.parametrize(
    ("pattern", "topic", "expected"),
    [
        ("sancho/#", "sancho/body/vision/evt/x", True),
        ("sancho/#", "sancho", True),
        ("sancho/body/+/evt/#", "sancho/body/vision/evt/person_entered", True),
        ("sancho/body/+/evt/#", "sancho/body/speech/cmd/say", False),
        ("sancho/body/+/evt/#", "sancho/body/evt/x", False),
        ("sancho/sys/body/health", "sancho/sys/body/health", True),
        ("sancho/sys/body/health", "sancho/sys/body/health/x", False),
        ("sancho/+", "sancho/a/b", False),
    ],
)
def test_topic_matches(pattern, topic, expected):
    assert topic_matches(pattern, topic) is expected


def test_may_publish():
    assert may_publish("body", "sancho/body/vision/evt/person_entered")
    assert not may_publish("body", "sancho/body/speech/cmd/say")
    assert not may_publish("recorder", "sancho/sys/recorder/health")


def test_acl_file_lists_only_environment_roles():
    prod = acl_text("prod")
    assert "user body" in prod and "user eval" not in prod and "user sim" not in prod
    assert "topic write sancho/body/+/evt/#" in prod
    assert "user eval" in acl_text("test")


def test_conf_denies_anonymous_and_limits_size():
    conf = conf_text(["127.0.0.1:1883", "@wlan0:1883"], "/mosquitto/config")
    assert "allow_anonymous false" in conf
    assert "max_packet_size 65536" in conf
    assert "listener 1883 127.0.0.1" in conf
    assert "listener 1883\nbind_interface wlan0" in conf
    assert "password_file /mosquitto/config/passwd" in conf


def test_password_hash_format():
    value = hash_password("secret", salt=b"0123456789ab")
    assert re.fullmatch(r"\$7\$101\$[A-Za-z0-9+/=]{16}\$[A-Za-z0-9+/=]{88}", value)


def test_generate_keeps_passwords_and_files_are_private(tmp_path):
    first = generate(tmp_path, "test", ["127.0.0.1:1883"])
    second = generate(tmp_path, "test", ["127.0.0.1:1883"])
    assert first == second and len(set(first.values())) == len(first)
    rotated = generate(tmp_path, "test", ["127.0.0.1:1883"], rotate=True)
    assert all(rotated[r] != first[r] for r in first)
    for path in [tmp_path / "passwd", tmp_path / "credentials" / "body"]:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "secret" not in (tmp_path / "passwd").read_text()


def test_switching_to_prod_removes_test_only_credentials(tmp_path):
    generate(tmp_path, "test", ["127.0.0.1:1883"])
    generate(tmp_path, "prod", ["127.0.0.1:1883"])
    remaining = {p.name for p in (tmp_path / "credentials").iterdir()}
    assert remaining == {r.name for r in roles_for("prod")}
