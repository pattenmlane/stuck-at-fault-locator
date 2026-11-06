"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    PIN_CIRCUIT = "pin_circuit"
    READ_CIRCUIT = "read_circuit"
    TEST_HYPOTHESIS = "test_hypothesis"
    REPORT_FAULT = "report_fault"


class Task(Enum):
    LOCATE_FAULT = "locate-fault"


SEED = "The case number, 1 to 100000: the same number always gives the same circuit"
NET = "The net suspected of being stuck"
STUCK = "The value the net is stuck at, 0 or 1"
INPUTS = "The primary input nets, in the order of a log entry's input bits"
OUTPUTS = "The primary output nets, in the order of a log entry's output bits"
GATES = "Every gate, each listed after the gates that feed it"
TRACES = "Each net's fault-free behaviour on the log"
LOG = "The fixed test log taken on the faulty device"


@dataclass
class Gate(Output):
    net: Annotated[str, "The net this gate drives"]
    kind: Annotated[str, "AND, OR, NAND, NOR, XOR or NOT"]
    inputs: Annotated[list[str], "The nets it reads: two, or one for NOT"]


@dataclass
class Trace(Output):
    net: Annotated[str, "The net"]
    values: Annotated[str, "Its fault-free value on each log entry: character i is for entry i"]
    reaches: Annotated[list[str], "The primary outputs this net can influence"]


@dataclass
class LogEntry(Output):
    inputs: Annotated[str, "The bits applied to the primary inputs"]
    expected: Annotated[str, "The primary output bits of a fault-free device"]
    observed: Annotated[str, "The primary output bits seen on the faulty device"]


@dataclass
class LocateInput(Output):
    seed: Annotated[int, SEED]


@dataclass
class CircuitOutput(Output):
    seed: Annotated[int, SEED]
    inputs: Annotated[list[str], INPUTS]
    outputs: Annotated[list[str], OUTPUTS]
    gates: Annotated[list[Gate], GATES]
    traces: Annotated[list[Trace], TRACES]
    log: Annotated[list[LogEntry], LOG]


@dataclass
class PinnedCircuitOutput(Output):
    # The answer key: the circuit and the fault planted in it, out of the agent's sight.
    seed: Annotated[int, SEED]
    inputs: Annotated[list[str], INPUTS]
    outputs: Annotated[list[str], OUTPUTS]
    gates: Annotated[list[Gate], GATES]
    traces: Annotated[list[Trace], TRACES]
    log: Annotated[list[LogEntry], LOG]
    net: Annotated[str, "The net the fault was planted on"]
    stuck_value: Annotated[int, "The value it was planted at"]


@dataclass
class HypothesisInput(Output):
    seed: Annotated[int, SEED]
    net: Annotated[str, NET]
    stuck_value: Annotated[int, STUCK]


@dataclass
class HypothesisOutput(Output):
    seed: Annotated[int, SEED]
    net: Annotated[str, NET]
    stuck_value: Annotated[int, STUCK]
    matches: Annotated[int, "How many log entries this fault reproduces exactly"]
    total: Annotated[int, "How many log entries there are"]


@dataclass
class ReportFaultInput(Output):
    seed: Annotated[int, SEED]
    net: Annotated[str, NET]
    stuck_value: Annotated[int, STUCK]


@dataclass
class FaultOutput(Output):
    seed: Annotated[int, SEED]
    path: Annotated[str, "The saved report, relative to the plugin workspace"]
    net: Annotated[str, NET]
    stuck_value: Annotated[int, STUCK]


TOOLS = {
    Tool.PIN_CIRCUIT: (LocateInput, PinnedCircuitOutput),
    Tool.READ_CIRCUIT: (LocateInput, CircuitOutput),
    Tool.TEST_HYPOTHESIS: (HypothesisInput, HypothesisOutput),
    Tool.REPORT_FAULT: (ReportFaultInput, FaultOutput),
}
TASKS = {Task.LOCATE_FAULT: (LocateInput, FaultOutput)}
