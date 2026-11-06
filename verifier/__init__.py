"""The deterministic verifier: every fault tried on truth tables, on contract instances. No model."""

from contract import Task, Tool

from .checks import result, saved_json
from .rules import MAX_SEED
from .task import fault_verdict, key_problem

TASKS = {Task.LOCATE_FAULT: fault_verdict}


def verify_input(tool, value):
    if not 1 <= value.seed <= MAX_SEED:
        return result(False, f"seed must be 1 to {MAX_SEED}")
    if Tool(tool) in (Tool.TEST_HYPOTHESIS, Tool.REPORT_FAULT) and value.stuck_value not in (0, 1):
        return result(False, "stuck_value must be 0 or 1")
    return result(True, "input is valid")


def verify_output(tool, input_value, output_value, workspace):
    if output_value.seed != input_value.seed:
        return result(False, "the output is for another seed")
    match Tool(tool):
        case Tool.PIN_CIRCUIT:
            problem = key_problem(input_value.seed, output_value)
            return result(not problem, problem or "the answer key holds")
        case Tool.READ_CIRCUIT:
            return result(bool(output_value.log), "the circuit has a log")
        case Tool.TEST_HYPOTHESIS:
            return result(0 <= output_value.matches <= output_value.total, "the count fits the log")
        case Tool.REPORT_FAULT:
            saved = saved_json(workspace, output_value.path)
            return result(saved is not None, "saved" if saved is not None else "nothing was saved")


def verify_task(task, arguments, output, reference, workspace):
    return TASKS[Task(task)](arguments, output, reference, workspace)
