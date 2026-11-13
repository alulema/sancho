"""Bench cases: valid and invalid (T5)."""

import copy

import pytest
import yaml

from contracts.cases import Case, InvalidCase, load_case
from tests.contract_docs import code_blocks

BLOCKS = code_blocks("casos-banco.md", "yaml")
FULL = yaml.safe_load(BLOCKS[0])


def case(**overrides) -> dict:
    data = copy.deepcopy(FULL)
    data.update(overrides)
    return data


def test_full_example_validates():
    parsed = Case.model_validate(FULL)
    assert parsed.id == "e0-greet-twice-within-window"
    assert [step.at_ms for step in parsed.when] == [0, 3000, 5000]
    assert parsed.given.config["greeting_window_min"] == 10


@pytest.mark.parametrize("block", BLOCKS[1:], ids=["invalid-json", "last-will"])
def test_step_examples_validate(block):
    fragment = yaml.safe_load(block)
    parsed = Case.model_validate(case(**{"expect": [], "forbid": [], **fragment}))
    assert parsed.when


def test_fractional_durations_are_allowed():
    assert Case.model_validate(case(given={"config": {"greeting_window_min": 0.05}}))


def test_load_case_from_file(tmp_path):
    path = tmp_path / "e0-greet.yaml"
    path.write_text(BLOCKS[0], encoding="utf-8")
    assert load_case(path).lang == "es"


def step(**action) -> dict:
    return {"at_ms": 0, **action}


PUBLISH = {"topic": "sancho/body/vision/evt/person_left", "payload": {}}

BAD = {
    "two actions in a step": {"when": [step(publish=PUBLISH, start={"component": "brain"})]},
    "no action in a step": {"when": [step()]},
    "steps out of order": {"when": [{**step(publish=PUBLISH), "at_ms": 10}, step(publish=PUBLISH)]},
    "negative at_ms": {"when": [{**step(publish=PUBLISH), "at_ms": -1}]},
    "unknown stop mode": {"when": [step(stop={"component": "brain", "mode": "gentle"})]},
    "wildcard topic": {"when": [step(publish={"topic": "sancho/#", "payload": {}})]},
    "topic outside sancho": {"when": [step(publish={"topic": "other/x", "payload": {}})]},
    "no steps": {"when": []},
    "nothing to check": {"expect": [], "forbid": []},
    "typo in a field": {"expect": [{"topic": PUBLISH["topic"], "count": 1, "whitin_ms": 10}]},
    "unknown top-level field": {"notes": "x"},
    "version as a number": {"version": 0.2},
    "unsupported major": {"version": "1.0"},
    "id without stage prefix": {"id": "greet-twice"},
    "unknown lang": {"lang": "fr"},
    "zero within_ms": {"forbid": [{"topic": PUBLISH["topic"], "count_gt": 0, "within_ms": 0}]},
    "config value not a scalar": {"given": {"config": {"window": [1, 2]}}},
}


@pytest.mark.parametrize("name", BAD, ids=str)
def test_invalid_case_is_rejected(name, tmp_path):
    path = tmp_path / "case.yaml"
    path.write_text(yaml.safe_dump(case(**BAD[name])), encoding="utf-8")
    with pytest.raises(InvalidCase):
        load_case(path)


def test_broken_yaml_is_rejected(tmp_path):
    path = tmp_path / "case.yaml"
    path.write_text("id: [unclosed", encoding="utf-8")
    with pytest.raises(InvalidCase):
        load_case(path)
