from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from slimconfig import build_output, plain_output

import verifier
from contract import (
    FaultOutput,
    Gate,
    HypothesisInput,
    HypothesisOutput,
    LocateInput,
    PinnedCircuitOutput,
    ReportFaultInput,
    Tool,
)
from plugin import pin_circuit, report_fault
from plugin.circuit import INPUTS
from verifier.checks import repeated
from verifier.rules import all_faults, behaviour, consistent_faults, log_matches, naive_guesses
from verifier.task import key_problem

SEED = 7
TASK = "locate-fault"
SEEDS = range(1, 301)


# The verifier gets contract instances, as NanoAgent's sandbox builds them from JSON.
def key(tmp_path: Path, seed: int = SEED) -> PinnedCircuitOutput:
    return build_output(plain_output(pin_circuit(LocateInput(seed), tmp_path)), PinnedCircuitOutput)


def judge(fault: tuple[str, int], tmp_path: Path, seed: int = SEED, reference=None) -> dict:
    made = report_fault(ReportFaultInput(seed, *fault), tmp_path)
    output = build_output(plain_output(made), FaultOutput)
    return verifier.verify_task(TASK, LocateInput(seed), output, reference or key(tmp_path, seed), str(tmp_path))


def first_case(tmp_path: Path, wanted) -> PinnedCircuitOutput:
    return next(case for case in (key(tmp_path, seed) for seed in SEEDS) if wanted(case))


def planted(case: PinnedCircuitOutput) -> tuple[str, int]:
    return case.net, case.stuck_value


def test_accepts_the_planted_fault(tmp_path: Path) -> None:
    verdict = judge(planted(key(tmp_path)), tmp_path)
    assert verdict["valid"] is True and verdict["score"] == 1.0


def test_accepts_a_fault_on_a_primary_input(tmp_path: Path) -> None:
    case = first_case(tmp_path, lambda case: case.net in INPUTS)
    assert judge(planted(case), tmp_path, case.seed)["valid"] is True


def test_accepts_an_equivalent_fault_on_another_net(tmp_path: Path) -> None:
    case = first_case(tmp_path, lambda case: len(consistent_faults(case)) > 1)
    other = next(fault for fault in consistent_faults(case) if fault != planted(case))
    assert other[0] != case.net
    verdict = judge(other, tmp_path, case.seed)
    assert verdict["valid"] is True and verdict["score"] == 1.0


def test_a_not_input_stuck_at_0_equals_its_output_stuck_at_1() -> None:
    circuit = SimpleNamespace(
        inputs=["a", "b", "c", "d"],
        outputs=["y0"],
        gates=[Gate("n1", "NOT", ["a"]), Gate("y0", "AND", ["n1", "b"])],
    )
    assert behaviour(circuit, ("a", 0)) == behaviour(circuit, ("n1", 1))
    assert behaviour(circuit, ("a", 1)) != behaviour(circuit, ("n1", 1))


def test_refuses_a_fault_matching_most_but_not_all_of_the_log(tmp_path: Path) -> None:
    case = key(tmp_path)
    total = len(case.log)
    near = next(fault for fault in all_faults(case) if log_matches(case, fault) == total - 1)
    verdict = judge(near, tmp_path)
    assert verdict["valid"] is False and verdict["details"]["failed"] == ["equivalent"]
    assert verdict["score"] == pytest.approx((total - 1) / total)


@pytest.mark.parametrize("seed", SEEDS)
def test_refuses_the_right_net_at_the_wrong_value(tmp_path: Path, seed: int) -> None:
    case = key(tmp_path, seed)
    verdict = judge((case.net, 1 - case.stuck_value), tmp_path, seed)
    assert verdict["valid"] is False and verdict["score"] < 1
    assert verdict["details"]["failed"] == ["equivalent"]


@pytest.mark.parametrize("seed", range(1, 41))
def test_refuses_every_naive_guess(tmp_path: Path, seed: int) -> None:
    case = key(tmp_path, seed)
    for fault in naive_guesses(case):
        assert judge(fault, tmp_path, seed)["valid"] is False


def test_only_equivalent_faults_pass(tmp_path: Path) -> None:
    case = key(tmp_path)
    passed = [fault for fault in all_faults(case) if judge(fault, tmp_path, reference=case)["valid"]]
    assert passed == consistent_faults(case)


def test_refuses_a_submission_with_nothing_saved(tmp_path: Path) -> None:
    case = key(tmp_path)
    output = FaultOutput(SEED, f"faults/{SEED}.json", *planted(case))
    verdict = verifier.verify_task(TASK, LocateInput(SEED), output, case, str(tmp_path))
    assert verdict["valid"] is False and verdict["details"]["failed"] == ["saved"]


def test_refuses_a_submission_that_differs_from_the_file(tmp_path: Path) -> None:
    case = key(tmp_path)
    report_fault(ReportFaultInput(SEED, case.net, 1 - case.stuck_value), tmp_path)
    output = FaultOutput(SEED, f"faults/{SEED}.json", *planted(case))
    verdict = verifier.verify_task(TASK, LocateInput(SEED), output, case, str(tmp_path))
    assert verdict["valid"] is False and "differs" in verdict["message"]


def test_repeated_handles_enums() -> None:
    # no Enum list in this plugin's outputs, so the helper is tested directly
    assert repeated([Tool.PIN_CIRCUIT, Tool.REPORT_FAULT, Tool.PIN_CIRCUIT, Tool.REPORT_FAULT]) == [
        Tool.PIN_CIRCUIT,
        Tool.REPORT_FAULT,
    ]


@pytest.mark.parametrize("path", ["faults/\0.json", "/etc/passwd", "", ".", "faults"])
def test_nonsense_paths_are_refused_without_raising(tmp_path: Path, path: str) -> None:
    case = key(tmp_path)
    report_fault(ReportFaultInput(SEED, *planted(case)), tmp_path)
    output = FaultOutput(SEED, path, *planted(case))
    assert verifier.verify_task(TASK, LocateInput(SEED), output, case, str(tmp_path))["details"]["failed"] == ["saved"]
    if path != "/etc/passwd":
        assert (
            verifier.verify_output("report_fault", ReportFaultInput(SEED, "a", 1), output, str(tmp_path))["valid"]
            is False
        )


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        "",
        "null",
        "[" * 100_000,
        "[" * 100_000 + "]" * 100_000,
        '{"seed": 7}',
        '{"seed": 7, "net": 1, "stuck_value": []}',
    ],
)
def test_refuses_a_malformed_file(tmp_path: Path, text: str) -> None:
    case = key(tmp_path)
    (tmp_path / "faults").mkdir()
    (tmp_path / "faults" / f"{SEED}.json").write_text(text)
    output = FaultOutput(SEED, f"faults/{SEED}.json", *planted(case))
    verdict = verifier.verify_task(TASK, LocateInput(SEED), output, case, str(tmp_path))
    assert verdict["valid"] is False and verdict["details"]["failed"] == ["saved"]


def test_refuses_another_path(tmp_path: Path) -> None:
    case = key(tmp_path)
    report_fault(ReportFaultInput(SEED, *planted(case)), tmp_path)
    output = FaultOutput(SEED, "../elsewhere.json", *planted(case))
    verdict = verifier.verify_task(TASK, LocateInput(SEED), output, case, str(tmp_path))
    assert verdict["details"]["failed"] == ["saved"]


def test_refuses_another_seed(tmp_path: Path) -> None:
    case = key(tmp_path)
    made = report_fault(ReportFaultInput(8, *planted(case)), tmp_path)
    verdict = verifier.verify_task(TASK, LocateInput(SEED), made, case, str(tmp_path))
    assert verdict["valid"] is False and verdict["details"]["failed"] == ["seed"]


@pytest.mark.parametrize(
    ("net", "value"),
    [("", 1), ("nope", 1), ("y2", 0), ("A", 1), ("a ", 1), ("a\n", 1), ("☃", 0), ("a", 2), ("a", -1), ("a", 10**30)],
)
def test_refuses_a_missing_or_unknown_fault(tmp_path: Path, net: str, value: int) -> None:
    verdict = judge((net, value), tmp_path)
    assert verdict["valid"] is False and verdict["score"] == 0.0
    assert verdict["details"]["failed"] == ["coverage"]


def test_refuses_a_missing_answer_key(tmp_path: Path) -> None:
    case = key(tmp_path)
    made = report_fault(ReportFaultInput(SEED, *planted(case)), tmp_path)
    verdict = verifier.verify_task(TASK, LocateInput(SEED), made, None, str(tmp_path))
    assert verdict["score"] == 0.0 and verdict["details"]["failed"] == ["answer-key"]


def shorter(case: PinnedCircuitOutput, keep: int) -> PinnedCircuitOutput:
    traces = [replace(trace, values=trace.values[:keep]) for trace in case.traces]
    return replace(case, log=case.log[:keep], traces=traces)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda case: replace(case, seed=8), "for seed 8"),
        (lambda case: replace(case, stuck_value=1 - case.stuck_value), "does not explain"),
        (lambda case: replace(case, net="n1"), "does not explain"),
        (lambda case: replace(case, log=[replace(e, observed=e.expected) for e in case.log]), "no failure"),
        (lambda case: replace(case, log=[replace(e, expected="00") for e in case.log]), "expected"),
        (lambda case: shorter(case, 1), "not equivalent"),
        (lambda case: replace(case, traces=[replace(case.traces[0], values="000000")]), "trace of a"),
        (lambda case: replace(case, traces=[replace(case.traces[0], reaches=[])]), "fan-out of a"),
    ],
)
def test_refuses_an_altered_answer_key(tmp_path: Path, change, reason: str) -> None:
    case = key(tmp_path)
    assert key_problem(SEED, case) is None
    problem = key_problem(SEED, change(case))
    assert reason in problem
    verdict = judge(planted(case), tmp_path, reference=change(case))
    assert verdict["score"] == 0.0 and verdict["details"]["failed"] == ["answer-key"]


def test_refuses_a_file_that_is_not_text(tmp_path: Path) -> None:
    case = key(tmp_path)
    (tmp_path / "faults").mkdir()
    (tmp_path / "faults" / f"{SEED}.json").write_bytes(b"\xff\xfe\x00")
    output = FaultOutput(SEED, f"faults/{SEED}.json", *planted(case))
    verdict = verifier.verify_task(TASK, LocateInput(SEED), output, case, str(tmp_path))
    assert verdict["details"]["failed"] == ["saved"]


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda case: replace(case, inputs=["a"]), "4 primary inputs"),
        (lambda case: replace(case, gates=[Gate("y0", "MUX", ["a", "b"])]), "malformed"),
        (lambda case: replace(case, gates=[Gate("y0", "AND", ["a"])]), "malformed"),
        (lambda case: replace(case, gates=[Gate("y0", "NOT", ["ghost"])]), "malformed"),
        (lambda case: replace(case, gates=list(reversed(case.gates))), "malformed"),
        (lambda case: replace(case, outputs=["a"]), "not driven"),
        (lambda case: replace(case, outputs=["ghost"]), "not driven"),
        (lambda case: replace(case, traces=[replace(case.traces[0], net="ghost")]), "unknown net"),
        (lambda case: replace(case, log=[replace(case.log[0], inputs="")]), "input bits"),
        (lambda case: replace(case, log=[replace(case.log[0], inputs="10x1")]), "input bits"),
        (lambda case: replace(case, log=[replace(case.log[0], inputs="10101")]), "input bits"),
        (lambda case: replace(case, log=[], traces=[]), "no failure"),
        (lambda case: replace(case, gates=[], outputs=[], traces=[], log=[]), "no failure"),
        (lambda case: replace(case, net="ghost"), "does not explain"),
    ],
)
def test_a_nonsense_answer_key_is_refused_without_raising(tmp_path: Path, change, reason: str) -> None:
    case = key(tmp_path)
    nonsense = change(case)
    assert reason in key_problem(SEED, nonsense)
    assert verifier.verify_output("pin_circuit", LocateInput(SEED), nonsense, "")["valid"] is False
    verdict = judge(planted(case), tmp_path, reference=nonsense)
    assert verdict["score"] == 0.0 and verdict["details"]["failed"] == ["answer-key"]


def test_a_nonsense_tool_output_does_not_raise(tmp_path: Path) -> None:
    given = HypothesisInput(SEED, "ghost", 7)
    assert verifier.verify_input("test_hypothesis", given)["valid"] is False
    assert (
        verifier.verify_output("test_hypothesis", given, HypothesisOutput(SEED, "ghost", 7, -1, 0), "")["valid"]
        is False
    )
    assert (
        verifier.verify_input("report_fault", ReportFaultInput(SEED, "ghost", 0))["valid"] is True
    )  # coverage judges it


def test_refuses_a_key_a_naive_guess_explains(tmp_path: Path) -> None:
    case = key(tmp_path)
    fault = ("y1", 1)
    row = behaviour(case, fault)
    log = [replace(e, observed=f"{row[0] >> int(e.inputs, 2) & 1}{row[1] >> int(e.inputs, 2) & 1}") for e in case.log]
    assert "naive" in key_problem(SEED, replace(case, log=log, net="y1", stuck_value=1))


def test_refuses_bad_tool_input() -> None:
    assert verifier.verify_input("read_circuit", LocateInput(0))["valid"] is False
    assert verifier.verify_input("read_circuit", LocateInput(100_001))["valid"] is False
    assert verifier.verify_input("read_circuit", LocateInput(100_000))["valid"] is True
    assert verifier.verify_input("test_hypothesis", HypothesisInput(1, "a", 2))["valid"] is False
    assert verifier.verify_input("report_fault", ReportFaultInput(1, "a", -1))["valid"] is False
    assert verifier.verify_input("report_fault", ReportFaultInput(1, "a", 1))["valid"] is True


def test_checks_tool_output(tmp_path: Path) -> None:
    given = HypothesisInput(1, "a", 0)
    assert verifier.verify_output("test_hypothesis", given, HypothesisOutput(1, "a", 0, 6, 6), "")["valid"] is True
    assert verifier.verify_output("test_hypothesis", given, HypothesisOutput(1, "a", 0, 7, 6), "")["valid"] is False
    assert verifier.verify_output("test_hypothesis", given, HypothesisOutput(2, "a", 0, 1, 6), "")["valid"] is False
    assert verifier.verify_output("pin_circuit", LocateInput(SEED), key(tmp_path), "")["valid"] is True


def test_the_saved_file_is_what_the_tool_reports(tmp_path: Path) -> None:
    given = ReportFaultInput(SEED, "a", 1)
    made = report_fault(given, tmp_path)
    assert json.loads((tmp_path / made.path).read_text()) == {"seed": SEED, "net": "a", "stuck_value": 1}
    assert verifier.verify_output("report_fault", given, made, str(tmp_path))["valid"] is True
    missing = FaultOutput(SEED, "faults/none.json", "a", 1)
    assert verifier.verify_output("report_fault", given, missing, str(tmp_path))["valid"] is False
