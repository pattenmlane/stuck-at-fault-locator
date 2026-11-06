from __future__ import annotations

import json
from pathlib import Path

from slimconfig import plain_output

from contract import FaultOutput, ReportFaultInput


def report_fault(given: ReportFaultInput, workspace: Path) -> FaultOutput:
    relative = f"faults/{given.seed}.json"
    path = workspace / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plain_output(given), indent=2), encoding="utf-8")
    return FaultOutput(given.seed, relative, given.net, given.stuck_value)
