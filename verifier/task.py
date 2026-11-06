"""The verdict on a reported fault: named checks, judged in order."""

from .checks import result, saved_json
from .rules import (
    OPERATIONS,
    VECTORS,
    all_faults,
    behaviour,
    bits,
    consistent_faults,
    fan_in,
    log_matches,
    naive_guesses,
    tables,
)


def shape_problem(pinned):
    """Why the circuit can't even be evaluated, or None, so nonsense is refused and never raises."""
    if 2 ** len(pinned.inputs) != VECTORS:
        return "the circuit needs 4 primary inputs"
    known = set(pinned.inputs)
    for gate in pinned.gates:
        reads = 1 if gate.kind == "NOT" else 2
        if gate.kind not in OPERATIONS or len(gate.inputs) != reads or not known.issuperset(gate.inputs):
            return f"the gate driving {gate.net} is malformed"
        known.add(gate.net)
    if not {gate.net for gate in pinned.gates}.issuperset(pinned.outputs):
        return "an output is not driven by a gate"
    if not known.issuperset(trace.net for trace in pinned.traces):
        return "a trace names an unknown net"
    if any(len(e.inputs) != len(pinned.inputs) or set(e.inputs) - set("01") for e in pinned.log):
        return "a log entry's input bits are malformed"
    return None


def data_problem(pinned):
    """Why the data shown to the agent is wrong, or None."""
    nets = tables(pinned)
    good = behaviour(pinned)
    if any(entry.expected != bits(good, entry) for entry in pinned.log):
        return "a log entry's expected outputs are wrong"
    for trace in pinned.traces:
        if trace.values != "".join(bits([nets[trace.net]], entry) for entry in pinned.log):
            return f"the trace of {trace.net} is wrong"
        if trace.reaches != [name for name in pinned.outputs if trace.net in fan_in(pinned.gates, name)]:
            return f"the fan-out of {trace.net} is wrong"
    return None


def key_problem(seed, pinned):
    """Why the answer key can't be trusted, or None. Every fault on every net is tried on the log."""
    if pinned is None:
        return "no answer key was pinned"
    if pinned.seed != seed:
        return f"the answer key is for seed {pinned.seed}, not {seed}"
    problem = shape_problem(pinned) or data_problem(pinned)
    if problem:
        return problem
    if all(entry.expected == entry.observed for entry in pinned.log):
        return "the log shows no failure, so the fault goes undetected"
    fits = consistent_faults(pinned)
    if (pinned.net, pinned.stuck_value) not in fits:
        return "the planted fault does not explain the log"
    if len({behaviour(pinned, fault) for fault in fits}) > 1:
        return "the log leaves two faults that are not equivalent"
    return "a naive guess explains the log" if set(naive_guesses(pinned)) & set(fits) else None


def saved_problem(output, workspace):
    expected = f"faults/{output.seed}.json"
    if output.path != expected:
        return f"the submission names {output.path!r}, not {expected!r}"
    saved = saved_json(workspace, expected)
    if saved is None:
        return f"no report is saved at {expected}: call report_fault before submitting"
    same = saved == {"seed": output.seed, "net": output.net, "stuck_value": output.stuck_value}
    return None if same else f"the submission differs from the report saved at {expected}"


def coverage_problem(output, pinned):
    if not output.net:
        return "no net was named"
    if output.stuck_value not in (0, 1):
        return f"a net sticks at 0 or 1, not {output.stuck_value}"
    return None if (output.net, output.stuck_value) in all_faults(pinned) else f"no such net: {output.net}"


def fault_verdict(arguments, output, reference, workspace):
    problem = key_problem(arguments.seed, reference)
    if problem:
        return result(False, f"answer-key: {problem}", score=0.0, failed=["answer-key"])
    if output.seed != arguments.seed:
        return result(False, f"seed: the submission is for seed {output.seed}", score=0.0, failed=["seed"])
    problem = saved_problem(output, workspace)
    if problem:
        return result(False, f"saved: {problem}", score=0.0, failed=["saved"])
    problem = coverage_problem(output, reference)
    if problem:
        return result(False, f"coverage: {problem}", score=0.0, failed=["coverage"])

    fault = (output.net, output.stuck_value)
    planted = (reference.net, reference.stuck_value)
    if behaviour(reference, fault) == behaviour(reference, planted):
        return result(True, f"All checks hold: {fault[0]} stuck at {fault[1]} acts as the hidden fault on all inputs")
    matches, total = log_matches(reference, fault), len(reference.log)
    message = f"equivalent: {fault[0]} stuck at {fault[1]} reproduces {matches} of {total} log entries"
    return result(False, message, score=min(matches / total, 0.99), failed=["equivalent"], expected=planted)
