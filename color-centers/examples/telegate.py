"""
A remote CNOT between two colour-centre QPUs, with a telegate.

Rank 0 lends its qubit, the control, to rank 1 with ``expose``. Rank 1 applies
a CNOT from it onto its own qubit, the target, and gives the control back with
``unexpose``. Behind the two calls the backend runs a cat-entangler and a
cat-disentangler over one heralded electron-electron pair, with the control on
a nuclear spin of rank 0 and the target on a nuclear spin of rank 1. On an
ideal network the input ``ct`` comes out as ``c`` on rank 0 and ``c XOR t`` on
rank 1.

Run from the plugin directory, with the plugin installed:

    netqmpi -n 2 examples/telegate.py --netqasm --plugin nv_2026 --metrics metrics.json

The input defaults to 10 and can be changed with TELEGATE_INPUT (two bits:
control, then target). The program prints how often its qubit came out
right, and what the plugin measured on the link (``comm.metrics``).
"""
import os
from statistics import mean

from netqmpi.sdk.environment import Environment

INPUT = os.environ.get("TELEGATE_INPUT", "10")


def main(env: Environment = None):
    comm = env.comm
    if comm.size != 2 or len(INPUT) != 2 or set(INPUT) - {"0", "1"}:
        raise ValueError("Run on 2 ranks, with TELEGATE_INPUT two bits (control, target).")
    control_bit, target_bit = int(INPUT[0]), int(INPUT[1])

    with comm:
        circuit = env.create_circuit(num_qubits=1, num_clbits=1)
        if comm.rank == 0 and control_bit:
            circuit.x(0)
        if comm.rank == 1 and target_bit:
            circuit.x(0)
        control = comm.expose(circuit, 0, [1], root=0)
        if comm.rank == 1:
            circuit.cx(control, 0)
        comm.unexpose(circuit, [1], root=0)
        circuit.measure(0, 0)

    # On the NetQASM backend the run is simulated when the last rank leaves
    # its block, so only that rank has its counts and the metrics here.
    counts = comm.results
    if not counts:
        return
    shots = sum(counts.values())
    if comm.rank == 0:
        role, expected = "control", control_bit
    else:
        role, expected = "target", control_bit ^ target_bit
    right = counts.get(str(expected), 0)
    print(f"input {INPUT}: rank {comm.rank} ({role}) reads {expected} in "
          f"{right}/{shots} = {right / shots:.4f} of the shots")

    link = comm.metrics.get("plugin")
    if link and link["epr_pairs"]:
        pairs = link["epr_pairs"]
        print(f"link: {pairs} pairs, {link['epr_attempts'] / pairs:.0f} attempts and "
              f"{mean(link['pair_time_ns']) / 1e6:.2f} ms per pair, "
              f"heralded fidelity {link['pair_fidelity']:.4f}")
    shot_times = comm.metrics.get("netqmpi", {}).get("sim_time_ns")
    if shot_times:
        print(f"simulated time per shot: {mean(shot_times) / 1e6:.2f} ms")
