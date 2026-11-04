"""
Distributed Exact Grover's Algorithm (DEGA) on colour-centre QPUs, in NetQMPI.

NetQMPI version of DEGA.py, from the original NetSquid emulator, for marked
states split into 2-bit chunks. Each rank owns one chunk and runs an exact
Grover search on two nuclear spins of its own QPU: one iteration finds a
2-qubit target with certainty, so the ranks never need to talk to each other.
The global answer is the concatenation of the local ones.

The gates are the same, in the same order, as in DEGA.py: the phase oracle
is MultiCPhase2 from primitives.py written with rz and cx, so with the
colour-centre plugin every rank runs the very physical instructions the
NetSquid version does.

Run from the plugin directory (color-centers/), with the plugin installed:

    netqmpi -n 2 examples/dega.py --netqasm \\
        --config examples/nv_2026.yaml

The marked state defaults to 1010 (two ranks) and can be changed with the
DEGA_MARKED_STATE environment variable; it needs 2 bits per rank.
"""
import os
from itertools import combinations

import numpy as np

from netqmpi.sdk.environment import Environment

MARKED_STATE = os.environ.get("DEGA_MARKED_STATE", "1010")
LOCAL_QUBITS = 2


def multi_controlled_phase(circuit, qubits, phase):
    """Phase ``phase`` on |1...1>: MultiCPhase2 from primitives.py."""
    base_angle = phase / 2 ** (len(qubits) - 1)
    for size in range(1, len(qubits) + 1):
        angle = base_angle if size % 2 == 1 else -base_angle
        for subset in combinations(qubits, size):
            *controls, accumulator = subset
            for control in controls:
                circuit.cx(control, accumulator)
            circuit.rz(angle, accumulator)
            for control in reversed(controls):
                circuit.cx(control, accumulator)


def oracle(circuit, marked):
    """Flip the phase of |marked>."""
    flips = [q for q, bit in enumerate(marked) if bit == "0"]
    for q in flips:
        circuit.x(q)
    multi_controlled_phase(circuit, list(range(len(marked))), np.pi)
    for q in flips:
        circuit.x(q)


def diffusion(circuit, num_qubits):
    for q in range(num_qubits):
        circuit.h(q)
    oracle(circuit, "0" * num_qubits)
    for q in range(num_qubits):
        circuit.h(q)


def main(env: Environment = None):
    comm = env.comm
    rank, size = comm.rank, comm.size

    if len(MARKED_STATE) != LOCAL_QUBITS * size or set(MARKED_STATE) - {"0", "1"}:
        raise ValueError(
            f"DEGA_MARKED_STATE must be {LOCAL_QUBITS * size} bits for {size} "
            f"ranks, got {MARKED_STATE!r}")
    local_target = MARKED_STATE[LOCAL_QUBITS * rank:LOCAL_QUBITS * (rank + 1)]

    with comm:
        circuit = env.create_circuit(num_qubits=LOCAL_QUBITS, num_clbits=LOCAL_QUBITS)
        for q in range(LOCAL_QUBITS):
            circuit.h(q)
        oracle(circuit, local_target)
        diffusion(circuit, LOCAL_QUBITS)
        # NetQMPI prints bit strings with clbit 0 last; measuring qubit q
        # into clbit n-1-q makes them read qubit 0 first, as DEGA.py does.
        for q in range(LOCAL_QUBITS):
            circuit.measure(q, LOCAL_QUBITS - 1 - q)

    # On the NetQASM backend the whole network is simulated when the last
    # rank leaves its block, so only that rank has its counts at this point.
    counts = comm.results
    if counts:
        shots = sum(counts.values())
        hits = counts.get(local_target, 0)
        print(f"rank {rank}: local target {local_target}, "
              f"P(success) = {hits}/{shots} = {hits / shots:.4f}, "
              f"counts = {dict(sorted(counts.items()))}")
