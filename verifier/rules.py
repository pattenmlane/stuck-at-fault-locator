"""Stuck-at faults on truth tables: a net is 16 bits, one per input vector, so a pass covers every vector."""

MAX_SEED = 100_000
VECTORS = 16
ONES = (1 << VECTORS) - 1
OPERATIONS = {
    "AND": lambda x, y: x & y,
    "OR": lambda x, y: x | y,
    "NAND": lambda x, y: ONES ^ (x & y),
    "NOR": lambda x, y: ONES ^ (x | y),
    "XOR": lambda x, y: x ^ y,
    "NOT": lambda x: ONES ^ x,
}


def tables(circuit, fault=None):
    """Every net's table, with ``fault`` (net, value) forced. Bit v is the net's value on vector v,
    reading the input bits as a binary number."""

    def forced(net, table):
        return (ONES if fault[1] else 0) if fault and fault[0] == net else table

    width = len(circuit.inputs)
    nets = {}
    for place, net in enumerate(circuit.inputs):
        shift = width - 1 - place
        nets[net] = forced(net, sum(1 << v for v in range(VECTORS) if v >> shift & 1))
    for gate in circuit.gates:
        nets[gate.net] = forced(gate.net, OPERATIONS[gate.kind](*(nets[name] for name in gate.inputs)))
    return nets


def behaviour(circuit, fault=None):
    """The outputs' tables: two faults with the same behaviour are equivalent."""
    nets = tables(circuit, fault)
    return tuple(nets[name] for name in circuit.outputs)


def bits(row, entry):
    """The bits of ``row``, a list of tables, on the vector a log entry applied."""
    return "".join(str(table >> int(entry.inputs, 2) & 1) for table in row)


def log_matches(circuit, fault):
    row = behaviour(circuit, fault)
    return sum(bits(row, entry) == entry.observed for entry in circuit.log)


def all_faults(circuit):
    return [(net, value) for net in [*circuit.inputs, *(g.net for g in circuit.gates)] for value in (0, 1)]


def consistent_faults(circuit):
    return [fault for fault in all_faults(circuit) if log_matches(circuit, fault) == len(circuit.log)]


def fan_in(gates, net):
    """``net`` and every net that feeds it. Gates are in order, so one backward pass finds them all."""
    found = {net}
    for gate in reversed(gates):
        if gate.net in found:
            found.update(gate.inputs)
    return found


def naive_guesses(circuit):
    """What a careless reader blames: an output net itself, or the first gate feeding a failing output."""
    failing = {
        name
        for entry in circuit.log
        for name, want, got in zip(circuit.outputs, entry.expected, entry.observed)
        if want != got
    }
    first = {next(g.net for g in circuit.gates if g.net in fan_in(circuit.gates, name)) for name in failing}
    return [(net, value) for net in sorted({*circuit.outputs, *first}) for value in (0, 1)]
