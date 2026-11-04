"""
The quantum processor of a colour-centre node.

Same instructions, topologies, noise and durations as NVProcessor2026 and
SnVProcessor2026 in processors.py, minus the photon emission position: the
link places the entangled state straight on the electron.
"""
from __future__ import annotations

import numpy as np
from netsquid.components.instructions import (
    INSTR_CXDIR, INSTR_H, INSTR_INIT, INSTR_MEASURE, INSTR_ROT_X, INSTR_ROT_Y,
    INSTR_ROT_Z, INSTR_SWAP, INSTR_X, INSTR_Y, INSTR_Z,
)
from netsquid.components.models import DepolarNoiseModel, T1T2NoiseModel
from netsquid.components.qprocessor import PhysicalInstruction, QuantumProcessor
from netsquid.qubits.operators import Operator

from netqmpi_colorcenters.parameters import DeviceParameters

#: Memory position of the electron spin, the communication qubit. The
#: nuclear spins follow it.
ELECTRON = 0


def build_qdevice(name: str, num_qubits: int, params: DeviceParameters) -> QuantumProcessor:
    """
    Build the processor of one node.

    Args:
        name: Name of the processor.
        num_qubits: Electron plus nuclear spins.
        params: Physical parameters of the device.

    Returns:
        The processor, raising on any instruction its topology forbids
        instead of failing silently.
    """
    carbons = list(range(1, num_qubits))
    electron_carbon = [(ELECTRON, carbon) for carbon in carbons]

    def depolar(prob: float) -> DepolarNoiseModel:
        return DepolarNoiseModel(depolar_rate=prob, time_independent=True)

    electron_gate_noise = depolar(params.electron_single_qubit_depolar_prob)
    carbon_gate_noise = depolar(params.carbon_z_rot_depolar_prob)

    instructions = [
        PhysicalInstruction(INSTR_INIT, duration=params.electron_init_duration,
                            topology=[ELECTRON],
                            quantum_noise_model=depolar(params.electron_init_depolar_prob)),
        *(PhysicalInstruction(instr, duration=params.electron_single_qubit_duration,
                              topology=[ELECTRON], quantum_noise_model=electron_gate_noise)
          for instr in (INSTR_X, INSTR_Y, INSTR_Z, INSTR_H, INSTR_ROT_X, INSTR_ROT_Y, INSTR_ROT_Z)),
        PhysicalInstruction(
            INSTR_MEASURE, duration=params.measure_duration, topology=[ELECTRON],
            meas_operators=[
                Operator("M0", np.diag([np.sqrt(1 - params.prob_error_0),
                                        np.sqrt(params.prob_error_1)])),
                Operator("M1", np.diag([np.sqrt(params.prob_error_0),
                                        np.sqrt(1 - params.prob_error_1)])),
            ]),
    ]
    if carbons:
        instructions += [
            PhysicalInstruction(INSTR_INIT, duration=params.carbon_init_duration,
                                topology=carbons,
                                quantum_noise_model=depolar(params.carbon_init_depolar_prob)),
            PhysicalInstruction(INSTR_ROT_Z, duration=params.carbon_z_rot_duration,
                                topology=carbons, quantum_noise_model=carbon_gate_noise),
            *(PhysicalInstruction(instr, duration=params.carbon_single_qubit_duration,
                                  topology=carbons, quantum_noise_model=carbon_gate_noise)
              for instr in (INSTR_H, INSTR_X, INSTR_ROT_X)),
            PhysicalInstruction(INSTR_CXDIR, duration=params.ec_two_qubit_gate_duration,
                                topology=electron_carbon,
                                quantum_noise_model=depolar(params.ec_gate_depolar_prob)),
            PhysicalInstruction(INSTR_SWAP, duration=params.magical_swap_gate_duration,
                                topology=electron_carbon,
                                quantum_noise_model=depolar(params.magical_swap_gate_depolar_prob)),
        ]

    memory_noise = ([T1T2NoiseModel(T1=params.electron_T1, T2=params.electron_T2)]
                    + [T1T2NoiseModel(T1=params.carbon_T1, T2=params.carbon_T2)] * len(carbons))

    qdevice = QuantumProcessor(name=name, num_positions=num_qubits,
                               mem_noise_models=memory_noise, phys_instructions=instructions)
    qdevice._fail_exception = True
    return qdevice
