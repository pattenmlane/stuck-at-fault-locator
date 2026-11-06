from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from slimconfig import plain_output

from contract import HypothesisInput, LocateInput, LogEntry
from plugin import read_circuit, score_hypothesis
from plugin.circuit import (
    INPUTS,
    LOG_SIZE,
    MAX_CANDIDATES,
    MIN_CANDIDATES,
    MIN_FAILING,
    VECTORS,
    _usable,
    build_case,
    candidates,
    outputs,
)
from verifier.rules import all_faults, behaviour, bits, consistent_faults, fan_in, log_matches, naive_guesses
from verifier.task import key_problem


def refault(case, net, value):
    """The same circuit and vectors, with the log retaken on another fault."""
    log = [LogEntry(e.inputs, e.expected, outputs(case.gates, e.inputs, (net, value))) for e in case.log]
    return replace(case, log=log, net=net, stuck_value=value)


@pytest.mark.parametrize("seed", range(1, 301))
def test_every_case_has_a_confirmed_answer_that_naive_blame_misses(seed: int) -> None:
    case = build_case(seed)
    assert key_problem(seed, case) is None
    fits = consistent_faults(case)
    assert not set(naive_guesses(case)) & set(fits)
    assert not {fault[0] for fault in fits} & set(case.outputs)
    assert behaviour(case, (case.net, case.stuck_value)) != behaviour(case)  # detectable


@pytest.mark.parametrize("seed", range(1, 301))
def test_every_case_fits_the_plan_in_the_instructions(seed: int) -> None:
    case = build_case(seed)
    found = candidates(case)
    assert MIN_CANDIDATES <= len(found) <= MAX_CANDIDATES
    assert set(found) & set(consistent_faults(case))  # the filter never drops the answer
    assert sum(entry.expected != entry.observed for entry in case.log) >= MIN_FAILING
    assert len(case.log) == LOG_SIZE and len(case.gates) == 8
    assert LOG_SIZE - 1 in [log_matches(case, fault) for fault in all_faults(case)]
    assert all(any(gate.net in fan_in(case.gates, name) for name in case.outputs) for gate in case.gates)


@pytest.mark.parametrize("seed", range(1, 31))
def test_the_two_evaluators_agree_on_every_fault(seed: int) -> None:
    case = build_case(seed)
    for fault in all_faults(case):
        row = behaviour(case, fault)
        entries = [LogEntry(vector, "", "") for vector in VECTORS]
        assert [bits(row, entry) for entry in entries] == [outputs(case.gates, vector, fault) for vector in VECTORS]


def test_the_generator_covers_inputs_and_equivalent_faults() -> None:
    cases = [build_case(seed) for seed in range(1, 301)]
    assert sum(case.net in INPUTS for case in cases) > 50
    assert sum(len(consistent_faults(case)) > 1 for case in cases) > 30


def test_the_generator_refuses_what_it_should() -> None:
    case = build_case(7)
    assert _usable(case)
    assert not _usable(replace(case, log=[replace(e, observed=e.expected) for e in case.log]))  # undetected
    assert not _usable(replace(case, log=case.log[:2]))  # too few vectors to settle it
    assert not _usable(refault(case, "y1", 1))  # the output net explains it
    assert not _usable(refault(case, "y0", 0))


def test_cases_are_reproducible_to_the_byte() -> None:
    digest = hashlib.sha256(json.dumps(plain_output(build_case(1)), sort_keys=True).encode()).hexdigest()
    assert digest == "87f9c55afeb672860ac55dd4807850935b9b7ff7abc06f50667f20fb2e9c747f"


def test_the_agent_never_sees_the_answer(tmp_path: Path) -> None:
    case = build_case(3)
    shown = plain_output(read_circuit(LocateInput(3), tmp_path))
    assert "net" not in shown and "stuck_value" not in shown
    assert shown["log"] == plain_output(case)["log"] and shown["gates"] == plain_output(case)["gates"]


def test_the_case_fits_the_agents_budget(tmp_path: Path) -> None:
    assert len(json.dumps(plain_output(read_circuit(LocateInput(1), tmp_path)))) < 6000


def test_hypotheses_are_counted_on_the_log(tmp_path: Path) -> None:
    case = build_case(7)
    for net, value in all_faults(case):
        made = score_hypothesis(HypothesisInput(7, net, value), tmp_path)
        assert made.total == LOG_SIZE and made.matches == log_matches(case, (net, value))


@pytest.mark.parametrize(("net", "value"), [("nope", 0), ("", 1), ("a", 2)])
def test_a_bad_hypothesis_raises(tmp_path: Path, net: str, value: int) -> None:
    with pytest.raises(ValueError):
        score_hypothesis(HypothesisInput(7, net, value), tmp_path)


@pytest.mark.parametrize("seed", [0, -1, 100_001])
def test_refuses_a_seed_out_of_range(seed: int) -> None:
    with pytest.raises(ValueError, match="seed"):
        build_case(seed)
