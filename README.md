# Stuck At Fault Locator

A `nanoagent.plugin/v0001` plugin. Its task gives an agent a small seeded logic
circuit with one hidden stuck-at fault and a test log from the faulty device, and
asks which net is stuck, and at what value. Everything runs offline: a case is
built from its seed alone.

## Tools

| Tool | Does | Code |
|---|---|---|
| `pin_circuit` | The answer key: the circuit and its planted fault, hidden from the agent | `src/plugin/circuit.py` |
| `read_circuit` | The netlist, the test log and each net's fault-free trace, without the answer | `src/plugin/circuit.py` |
| `test_hypothesis` | Simulates one candidate fault and counts the log entries it reproduces | `src/plugin/circuit.py` |
| `report_fault` | Saves the net and stuck value to `faults/<seed>.json` | `src/plugin/report.py` |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `locate-fault` | Finds and saves the fault that explains the log | `agent`, with `read_circuit`, `test_hypothesis` and `report_fault`; reference `pin_circuit` |

## Verification

The planted fault is the answer key, and the verifier checks it instead of
trusting it. With its own evaluator, which runs every net as a 16-bit truth
table where the generator simulates one vector at a time, it tries both stuck
values on every net against the log. It refuses the key unless the log shows a
failure, the planted fault fits, every fault that fits is equivalent to it on all
16 input vectors, and no naive guess fits. A naive guess is an output net itself,
or the first gate feeding a failing output, at either stuck value.

It then reads the saved file, not just the submission, and judges in order:
`answer-key`, `seed`, `saved`, `coverage`, `equivalent`. A fault passes when its
outputs equal the planted fault's on all 16 vectors, so a fault on another net
that behaves the same is accepted. Integrity failures score 0. A wrong fault
scores the share of log entries it reproduces, which is always below 1.

## Limitations

- A report saved by an earlier run with the same seed still counts if the agent
  submits it without saving again. The answer is right either way.
- Faults are on whole nets: a net that fans out to several gates sticks for all of
  them, and single branches of a net are not modelled.
- `test_hypothesis` can be called on every fault, so a patient agent can find the
  answer without reasoning. The step and token limits make that the harder route.
- Cases are small, to fit the hosted agent's step and token limits.

## Layout

```text
.
├── nanoagent.yaml   # manifest (a slimconfig ManifestConfig): id, runtime, permissions, tools, tasks
├── contract.py      # each tool's and task's typed input and output: slimconfig Output classes
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # environment variable NAMEs this plugin needs, never values
├── src/plugin/      # the MCP server, the seeded generator and simulator, and the report writer
├── tests/
├── ui/              # how the page draws the outputs: renderers.js and renderers.css
├── product/         # the product page a catalog shows: product.yaml and icon.svg
└── verifier/        # deterministic verifier package
```

`contract.py` is the one place a value's shape is declared. Its `Output`
classes are the JSON Schemas the server offers and the agent sees, and every
input and output is built into its class on the way in and out: the server,
NanoAgent and the verifier all get typed values, never loose dicts. A tool
that fails raises; NanoAgent sees an MCP error.

To add a tool: add a `Tool` member, its input and output classes and its
`TOOLS` entry to `contract.py` (a snake_case name, classes named `...Input`
and `...Output`); write its implementation in `src/plugin/`, taking its input
and the workspace and returning its output; write its `verify_input` /
`verify_output` in `verifier/`, and tests for both. Then register it in
`src/plugin/__main__.py` (`IMPLEMENTATIONS`), `verifier/__init__.py` (`TOOLS`),
`nanoagent.yaml` (`tools`) and this README's Tools table; a task goes in its
Tasks table.

`LICENSE` stays the template's MIT license under your name, `.gitignore`
keeps its entries, and this README keeps its title and sections: NanoAgent refuses a plugin
that changes them (rule 10 of `nanoagent.plugin.manifest`). Renaming the
plugin means renaming it in `nanoagent.yaml` and this title together.

To add a task, add a `Task` member (a kebab-case id) and its `TASKS` input and
output classes to `contract.py`, and declare it in `nanoagent.yaml` with its `runner` (`tool`,
`agent` or `decide`) and a `reference` tool, or `null` if it has none. A `tool`
task's classes are its tool's; an `agent` task's agent ends by calling `submit`
with the task's output; a `decide` task's model only chooses, and every tool
argument and output field is an Enum or bool, or copied from a value of exactly
its type in the task's input or an earlier tool output. Then add the check of
its output, `verify_task(arguments, output, reference, workspace)`, to `TASKS`
in `verifier/__init__.py`. People use the plugin by chatting with its agent,
which runs its tasks and shows each output on the page (see `ui/`).

## Develop and run

```bash
uv sync --extra dev
uv run pytest
```

Publishing checks every plugin rule: push the plugin to a public GitHub
repository and run `rush publish <server> <github-url>`.
