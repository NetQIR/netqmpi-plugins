"""
Entanglement between colour centres: entanglement.py on SquidASM.

entanglement.py generates electron-electron pairs with netsquid-nv's
``NVDoubleClickMagicDistributor`` over a ``MiddleHeraldedConnection``.
netsquid-nv cannot be installed next to SquidASM -- it needs netsquid-magic
13, SquidASM ships 16 -- so its distributor is reproduced here on top of
netsquid-magic 16, whose double-click state model is the same:

* the delivered state and success probability are netsquid-magic's
  double-click model, with the parameters entanglement.py passes;
* after each delivery the nuclear spins of both nodes are dephased as
  netsquid-nv does: ``(1 - alpha)/2 (1 - exp(-(delta_w tau)^2 / 2))`` per
  attempt with ``alpha = 1/2``, and once more by ``initial_nuclear_phase``,
  everything twice because the double-click protocol re-initialises the
  electron twice per attempt.

Like entanglement.py, the pair is then turned into Phi+ by X (and Z for
Psi-) on the electron of node A, as physical instructions, and reported as
Phi+. Leaving the correction to NetQASM would not do: NetQASM 2.0 applies
it to virtual qubit 0 whatever the pair's qubit is (``Builder.
_build_cmds_epr_keep_corrections`` overwrites the qubit register with 0),
so a node that already held a qubit corrected that one instead.
"""
from __future__ import annotations

from typing import List

import numpy as np
from netsquid.components.instructions import INSTR_X, INSTR_Z
from netsquid.components.qprogram import QuantumProgram
from netsquid.nodes import Node
from netsquid.qubits.ketstates import BellIndex
from netsquid.qubits.qubitapi import apply_pauli_noise
from netsquid_magic.magic_distributor import DoubleClickMagicDistributor
from netsquid_magic.model_parameters import DoubleClickModelParameters
from squidasm.sim.network.network import MagicNetworkLayerProtocol

from netqmpi_colorcenters.device import ELECTRON
from netqmpi_colorcenters.parameters import LinkParameters


class ElectronLinkLayer(MagicNetworkLayerProtocol):
    """
    SquidASM's link layer, entangling electrons only.

    SquidASM places each half of a pair on the lowest free position of its
    node: with the electron busy, a nuclear spin, which cannot be entangled
    optically. Generation waits instead until both electrons are free, which
    the executors see to before they ask for a pair.
    """

    def _get_unused_memory_positions(self):
        if any(node.qmemory.mem_positions[ELECTRON].in_use for node in self.nodes):
            return None
        # With the electron free, the lowest free position is the electron.
        return super()._get_unused_memory_positions()


class NVDoubleClickMagicDistributor(DoubleClickMagicDistributor):
    """
    Double-click pairs plus the nuclear dephasing of netsquid-nv's
    distributor, delivered as Phi+ the way entanglement.py's Entangler does.
    """

    #: Bright-state population of the double-click protocol.
    ALPHA = 0.5

    def __init__(self, nodes: List[Node], model_params: DoubleClickModelParameters,
                 product_tau_decay_delta_w: float, initial_nuclear_phase: float = 0.0, **kwargs):
        super().__init__(nodes=nodes, model_params=model_params, **kwargs)
        self._p_induced = ((1 - self.ALPHA) / 2
                           * (1 - np.exp(-product_tau_decay_delta_w ** 2 / 2)))
        self._p_initial = 0.5 * (1 - np.exp(-initial_nuclear_phase ** 2))

    def _apply_noise(self, delivery, quantum_memory, positions):
        attempts = int(delivery.sample.delivery_duration
                       / self._model_parameters[0].cycle_time)
        nuclear = [qubit
                   for position in range(quantum_memory.num_positions)
                   if position != ELECTRON and quantum_memory.mem_positions[position].in_use
                   for qubit in quantum_memory.peek(position) if qubit is not None]
        for _ in range(2):
            _dephase(nuclear, self._p_initial, 1)
            _dephase(nuclear, self._p_induced, attempts)

        if quantum_memory is self.nodes[0][0].qmemory:
            self._correct_to_phi_plus(quantum_memory, bell_index=delivery.sample.label[1])

    @staticmethod
    def _correct_to_phi_plus(qmemory, bell_index: BellIndex) -> None:
        """X, and Z for Psi-, on the electron of node A: Psi+/Psi- become Phi+."""
        if qmemory.busy:
            raise RuntimeError(
                f"{qmemory.name} is running a program when its half of a pair arrives, "
                "so the pair cannot be corrected to Phi+.")
        program = QuantumProgram()
        program.apply(INSTR_X, [ELECTRON])
        if bell_index == BellIndex.PSI_MINUS:
            program.apply(INSTR_Z, [ELECTRON])
        qmemory.execute_program(program)

    def get_bell_state(self, midpoint_outcome) -> BellIndex:
        super().get_bell_state(midpoint_outcome)  # checks the outcome is a success
        return BellIndex.PHI_PLUS


def _dephase(qubits, probability: float, times: int) -> None:
    """Dephase each qubit as ``times`` dephasing channels of ``probability`` in a row."""
    keep = (1 + (1 - 2 * probability) ** times) / 2
    for qubit in qubits:
        apply_pauli_noise(qubit, (keep, 0., 0., 1. - keep))


def build_distributor(nodes: List[Node], link: LinkParameters) -> NVDoubleClickMagicDistributor:
    """
    The distributor entanglement.py builds, for one pair of nodes.

    Args:
        nodes: The two nodes, "A" side first.
        link: Physical parameters of the link.
    """
    half = link.length / 2
    model = DoubleClickModelParameters(
        length_A=half, length_B=half,
        speed_of_light_A=link.c, speed_of_light_B=link.c,
        emission_duration_A=link.photon_emission_delay,
        emission_duration_B=link.photon_emission_delay,
        p_loss_length_A=link.p_loss_lengths_with_conversion,
        p_loss_length_B=link.p_loss_lengths_with_conversion,
        p_loss_init_A=0., p_loss_init_B=0.,
        detector_efficiency=link.total_detection_eff,
        dark_count_probability=link.prob_dark_count,
        visibility=link.visibility,
        emission_fidelity_A=link.emission_fidelity,
        emission_fidelity_B=link.emission_fidelity,
        coin_prob_ph_ph=link.coin_prob_ph_ph,
        coin_prob_ph_dc=link.coin_prob_ph_dc,
        coin_prob_dc_dc=link.coin_prob_dc_dc,
    )
    return NVDoubleClickMagicDistributor(
        nodes=nodes, model_params=model,
        product_tau_decay_delta_w=link.product_tau_decay_delta_w,
        initial_nuclear_phase=link.initial_nuclear_phase)
