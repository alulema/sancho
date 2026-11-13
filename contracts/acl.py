"""E0 bus roles and permissions (ACL table of docs/contratos/topicos-e0.md, v0.4).

The broker enforces these; components also check before publishing so a mistake
fails loudly in the component instead of being dropped silently by the broker.
"""

from dataclasses import dataclass

PROD = "prod"
TEST = "test"
ENVIRONMENTS = (PROD, TEST)


@dataclass(frozen=True)
class Role:
    name: str
    environments: tuple[str, ...]
    publish: tuple[str, ...]
    subscribe: tuple[str, ...]


_BODY_PUBLISH = ("sancho/body/+/evt/#", "sancho/sys/body/health")
_BODY_SUBSCRIBE = ("sancho/body/+/cmd/#", "sancho/sys/#")

ROLES: dict[str, Role] = {
    role.name: role
    for role in (
        Role("body", (PROD, TEST), _BODY_PUBLISH, _BODY_SUBSCRIBE),
        Role(
            "brain",
            (PROD, TEST),
            ("sancho/body/+/cmd/#", "sancho/sys/brain/health"),
            ("sancho/body/+/evt/#", "sancho/sys/#"),
        ),
        Role("recorder", (PROD, TEST), (), ("sancho/#",)),
        # Test-only roles: the production broker has no credentials for them.
        Role("sim", (TEST,), _BODY_PUBLISH, _BODY_SUBSCRIBE),
        Role("replay", (TEST,), ("sancho/body/+/evt/#",), ()),
        Role("eval", (TEST,), ("sancho/#",), ("sancho/#",)),
    )
}

# The health topic each service publishes; tools publish none.
HEALTH_OF_ROLE = {"body": "body", "brain": "brain", "sim": "body"}


def roles_for(environment: str) -> list[Role]:
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unknown environment {environment!r}")
    return [role for role in ROLES.values() if environment in role.environments]


def topic_matches(pattern: str, topic: str) -> bool:
    """MQTT filter matching: `+` is one level, a trailing `#` is any number of levels."""
    pattern_levels = pattern.split("/")
    topic_levels = topic.split("/")
    for i, level in enumerate(pattern_levels):
        if level == "#":
            return i == len(pattern_levels) - 1
        if i >= len(topic_levels) or (level != "+" and level != topic_levels[i]):
            return False
    return len(pattern_levels) == len(topic_levels)


def may_publish(role: str, topic: str) -> bool:
    return any(topic_matches(pattern, topic) for pattern in ROLES[role].publish)
