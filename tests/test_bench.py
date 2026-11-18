"""T11: the bench's cases, its verification rules and a run against the components."""

import json
from pathlib import Path

import pytest

from contracts.cases import Case, load_case
from deploy.broker.local import PULL_HINT, broker_available
from eval.runner import (
    CASES_DIR,
    Observed,
    duration_ms,
    envelope_for,
    report,
    run_case,
    save,
    verify,
)
from tests.contract_docs import code_blocks

SAY = "sancho/body/speech/cmd/say"
needs_broker = pytest.mark.skipif(
    not broker_available(), reason=f"no broker: run `{PULL_HINT}` or set MOSQUITTO"
)

REQUIRED = {  # SPEC_E0 T11: at least these five situations
    "e0-greet-single-entry",
    "e0-greet-twice-within-window",
    "e0-greet-again-after-window",
    "e0-invalid-message-ignored",
    "e0-brain-down-no-greeting",
}


def all_cases() -> dict[str, Case]:
    return {load_case(f).id: load_case(f) for f in sorted(CASES_DIR.glob("*.yaml"))}


def test_every_case_loads_and_the_required_ones_exist():
    cases = all_cases()
    assert REQUIRED <= set(cases)
    for path in CASES_DIR.glob("*.yaml"):
        assert load_case(path).id == path.stem  # one file per case, named by its id


def test_the_contract_example_is_a_bench_case():
    """The first example of casos-banco.md is the twice-within-window case."""
    import yaml

    example = Case.model_validate(yaml.safe_load(code_blocks("casos-banco.md", "yaml")[0]))
    assert example == all_cases()["e0-greet-twice-within-window"]


# --- verification -----------------------------------------------------------------


def case(expect=(), forbid=(), when=None):
    return Case.model_validate({
        "id": "e0-test", "version": "0.3", "description": "x", "lang": "es",
        "when": when or [{"at_ms": 0, "publish_raw": {"topic": SAY, "text": "x"}}],
        "expect": list(expect), "forbid": list(forbid),
    })  # fmt: skip


def say_at(t_ms, payload=None, retained=False):
    return Observed(t_ms, SAY, retained, {"payload": payload or {"lang": "es"}})


def test_expect_is_a_minimum():
    c = case(expect=[{"topic": SAY, "count": 1, "within_ms": 1000}])
    assert not verify(c, [])[0].ok
    assert verify(c, [say_at(10)])[0].ok
    assert verify(c, [say_at(10), say_at(20)])[0].ok  # the maximum is forbid's job


def test_forbid_is_a_maximum():
    c = case(forbid=[{"topic": SAY, "count_gt": 1, "within_ms": 1000}])
    assert verify(c, [say_at(10)])[0].ok
    check = verify(c, [say_at(10), say_at(20)])[0]
    assert not check.ok and check.observed == 2


def test_only_messages_inside_the_window_and_not_retained_count():
    c = case(expect=[{"topic": SAY, "count": 1, "within_ms": 1000}])
    for observed in ([say_at(1500)], [say_at(-1)], [say_at(10, retained=True)]):
        assert not verify(c, observed)[0].ok


def test_payload_is_a_partial_match():
    c = case(expect=[{"topic": SAY, "count": 1, "within_ms": 1000,
                      "payload": {"lang": "es"}}])  # fmt: skip
    assert verify(c, [say_at(5, {"lang": "es", "text": "Hola"})])[0].ok
    assert not verify(c, [say_at(5, {"lang": "en"})])[0].ok
    assert not verify(c, [Observed(5, SAY, False, None)])[0].ok  # not JSON


def test_case_lasts_until_its_longest_window_or_last_step():
    assert duration_ms(all_cases()["e0-greet-twice-within-window"]) == 8000
    late = case(expect=[{"topic": SAY, "count": 0, "within_ms": 100}],
                when=[{"at_ms": 900, "publish_raw": {"topic": SAY, "text": "x"}}])  # fmt: skip
    assert duration_ms(late) == 900


def test_publish_wraps_the_payload_without_validating_it():
    data = json.loads(envelope_for("sancho/body/vision/evt/person_entered", {"confidence": 9}))
    assert data["type"] == "vision.person_entered" and data["source"] == "eval"
    assert data["payload"] == {"confidence": 9}


def test_results_carry_date_commit_and_counts(tmp_path):
    from contracts.types import utc_now
    from eval.runner import CaseResult

    results = [CaseResult("e0-a", "a.yaml", "pass", 1.0), CaseResult("e0-b", "b.yaml", "fail", 2.0)]
    data = report(results, utc_now())
    assert data["summary"] == {"pass": 1, "fail": 1, "error": 0}
    assert data["cases_version"] == "0.3" and data["commit"]
    path = save(data, tmp_path)
    assert path.name.endswith(f"-{data['commit']}.json")
    assert json.loads(path.read_text())["cases"][1]["result"] == "fail"


def test_invalid_config_is_an_error_not_a_failure(tmp_path):
    bad = Case.model_validate({**case(expect=[{"topic": SAY, "count": 1, "within_ms": 10}])
                              .model_dump(), "given": {"config": {"volume": 11}}})  # fmt: skip
    result = run_case(bad, Path("x.yaml"), tmp_path)  # fails before starting anything
    assert result.result == "error" and "given.config" in result.error


# --- against the real components --------------------------------------------------


@needs_broker
@pytest.mark.parametrize("case_id", ["e0-greet-single-entry", "e0-brain-down-no-greeting"])
def test_case_passes_against_the_components(tmp_path, case_id):
    c = all_cases()[case_id]
    result = run_case(c, CASES_DIR / f"{case_id}.yaml", tmp_path)
    assert result.result == "pass", result
