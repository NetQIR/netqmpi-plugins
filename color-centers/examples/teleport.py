"""
Teleporting a qubit between two colour-centre QPUs, in NetQMPI.

Rank 0 prepares a state on a nuclear spin and sends it to rank 1 with
``qsend``; rank 1 receives it with ``qrecv`` and measures it in the basis
it was prepared in, so a perfect network would always read 0. Behind the two
calls the backend runs the teledata protocol over the plugin's heralded link
(entanglement.py in the original emulator): an electron-electron pair, a Bell
measurement on rank 0 and the corrections on rank 1.

Run with the plugin installed:

    netqmpi -n 2 examples/teleport.py --netqasm --plugin snv_2026

The state is |1> by default; TELEPORT_STATE picks 0, 1, + or -. A
superposition shows how much phase the nuclear spin loses while the pair is
being generated.
"""
import os

from netqmpi.sdk.environment import Environment

STATE = os.environ.get("TELEPORT_STATE", "1")


def main(env: Environment = None):
    comm = env.comm
    if comm.size != 2 or STATE not in ("0", "1", "+", "-"):
        raise ValueError("Run on 2 ranks, with TELEPORT_STATE one of 0, 1, + and -.")

    with comm:
        circuit = env.create_circuit(num_qubits=1, num_clbits=1)
        if comm.rank == 0:
            if STATE in ("1", "-"):
                circuit.x(0)
            if STATE in ("+", "-"):
                circuit.h(0)
            comm.qsend(circuit, [0], 1)
        else:
            comm.qrecv(circuit, [0], 0)
            # Undo the preparation: an ideal transfer reads 0.
            if STATE in ("+", "-"):
                circuit.h(0)
            if STATE in ("1", "-"):
                circuit.x(0)
            circuit.measure(0, 0)

    counts = comm.results
    if comm.rank == 1 and counts:
        shots = sum(counts.values())
        print(f"teleported |{STATE}>: P(arrived intact) = {counts.get('0', 0)}/{shots} "
              f"= {counts.get('0', 0) / shots:.4f}")
