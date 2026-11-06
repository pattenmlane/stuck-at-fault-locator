"""Plants a fault in a seeded circuit and simulates it one vector at a time (the verifier uses truth tables)."""

from __future__ import annotations

from itertools import product
from pathlib import Path

from contract import (
    CircuitOutput,
    Gate,
    HypothesisInput,
    HypothesisOutput,
    LocateInput,
    LogEntry,
    PinnedCircuitOutput,
    Trace,
)
from plugin.rng import Rng
from verifier.rules import MAX_SEED, fan_in, naive_guesses

INPUTS = ("a", "b", "c", "d")
INTERNAL = ("n1", "n2", "n3", "n4", "n5", "n6")
OUTPUTS = ("y0", "y1")
VECTORS = ["".join(bits) for bits in product("01", repeat=len(INPUTS))]
LOG_SIZE = 6
MIN_FAILING = 2
MIN_CANDIDATES, MAX_CANDIDATES = 2, 6
ATTEMPTS = 5000
LOGIC = {
    "AND": all,
    "OR": any,
    "NAND": lambda seen: not all(seen),
    "NOR": lambda seen: not any(seen),
    "XOR": lambda seen: seen[0] != seen[1],
    "NOT": lambda seen: not seen[0],
}


def settle(gates: list[Gate], vector: str, fault: tuple[str, int] | None = None) -> dict[str, int]:
    """Every net's value on one vector."""
    values: dict[str, int] = {}

    def drive(net: str, value: int) -> None:
        values[net] = fault[1] if fault and fault[0] == net else int(value)

    for net, bit in zip(INPUTS, vector):
        drive(net, int(bit))
    for gate in gates:
        drive(gate.net, LOGIC[gate.kind]([values[name] for name in gate.inputs]))
    return values


def outputs(gates: list[Gate], vector: str, fault: tuple[str, int] | None = None) -> str:
    values = settle(gates, vector, fault)
    return "".join(str(values[net]) for net in OUTPUTS)


def _gates(rng: Rng) -> list[Gate]:
    pool, unread, gates = list(INPUTS), list(INPUTS), []
    for net in (*INTERNAL, *OUTPUTS):
        kind = rng.pick(list(LOGIC))
        first = rng.pick(unread or pool)  # unread nets first, so nearly every gate ends up reaching an output
        reads = [first] if kind == "NOT" else [first, rng.pick([name for name in pool if name != first])]
        unread = [name for name in unread if name not in reads]
        gates.append(Gate(net, kind, reads))
        if net in INTERNAL:
            pool.append(net)
            unread.append(net)
    return gates if not unread else []


def _fits(gates: list[Gate], log: list[LogEntry], fault: tuple[str, int]) -> int:
    return sum(outputs(gates, entry.inputs, fault) == entry.observed for entry in log)


def candidates(case: PinnedCircuitOutput) -> list[tuple[str, int]]:
    """The faults that survive the instructions' filter: reaching every failing output, and holding
    the opposite value on every failing vector."""
    failing = [i for i, entry in enumerate(case.log) if entry.expected != entry.observed]
    wrong = {
        name
        for i in failing
        for name, want, got in zip(OUTPUTS, case.log[i].expected, case.log[i].observed)
        if want != got
    }
    found = []
    for trace in case.traces:
        seen = {trace.values[i] for i in failing}
        if wrong <= set(trace.reaches) and len(seen) == 1:
            found.append((trace.net, 1 - int(seen.pop())))
    return found


def _usable(case: PinnedCircuitOutput) -> bool:
    def behaviour(fault: tuple[str, int]) -> list[str]:
        return [outputs(case.gates, vector, fault) for vector in VECTORS]

    # an undetectable fault never fails a vector, so this refuses those too
    if sum(entry.expected != entry.observed for entry in case.log) < MIN_FAILING:
        return False
    planted = (case.net, case.stuck_value)
    nets = (*INPUTS, *INTERNAL, *OUTPUTS)
    scores = {(net, value): _fits(case.gates, case.log, (net, value)) for net in nets for value in (0, 1)}
    fits = [fault for fault, score in scores.items() if score == LOG_SIZE]
    return (
        all(behaviour(fault) == behaviour(planted) for fault in fits)  # the log settles it
        and not set(naive_guesses(case)) & set(fits)
        and LOG_SIZE - 1 in scores.values()  # a near miss, so the count has to be read
        and MIN_CANDIDATES <= len(candidates(case)) <= MAX_CANDIDATES  # one parallel batch covers them
    )


def _attempt(seed: int, attempt: int) -> PinnedCircuitOutput | None:
    rng = Rng(f"circuit:{seed}:{attempt}")
    gates = _gates(rng)
    if not gates:
        return None
    fault = (rng.pick((*INPUTS, *INTERNAL)), rng.below(2))
    vectors = rng.shuffled(VECTORS)[:LOG_SIZE]
    log = [LogEntry(vector, outputs(gates, vector), outputs(gates, vector, fault)) for vector in vectors]
    states = [settle(gates, vector) for vector in vectors]
    traces = [
        Trace(
            net,
            "".join(str(state[net]) for state in states),
            [name for name in OUTPUTS if net in fan_in(gates, name)],
        )
        for net in (*INPUTS, *INTERNAL, *OUTPUTS)
    ]
    case = PinnedCircuitOutput(seed, list(INPUTS), list(OUTPUTS), gates, traces, log, *fault)
    return case if _usable(case) else None


def build_case(seed: int) -> PinnedCircuitOutput:
    if not 1 <= seed <= MAX_SEED:
        raise ValueError(f"seed must be 1 to {MAX_SEED}, got {seed}")
    for attempt in range(ATTEMPTS):
        case = _attempt(seed, attempt)
        if case is not None:
            return case
    raise RuntimeError(f"no usable circuit for seed {seed} in {ATTEMPTS} attempts")


def pin_circuit(given: LocateInput, workspace: Path) -> PinnedCircuitOutput:
    return build_case(given.seed)


def read_circuit(given: LocateInput, workspace: Path) -> CircuitOutput:
    case = build_case(given.seed)
    return CircuitOutput(case.seed, case.inputs, case.outputs, case.gates, case.traces, case.log)


def score_hypothesis(given: HypothesisInput, workspace: Path) -> HypothesisOutput:
    case = build_case(given.seed)
    if given.net not in (trace.net for trace in case.traces):
        raise ValueError(f"no such net: {given.net}")
    if given.stuck_value not in (0, 1):
        raise ValueError(f"stuck_value must be 0 or 1, got {given.stuck_value}")
    matches = _fits(case.gates, case.log, (given.net, given.stuck_value))
    return HypothesisOutput(given.seed, given.net, given.stuck_value, matches, len(case.log))
