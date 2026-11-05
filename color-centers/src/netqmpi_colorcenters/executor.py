"""
How a colour-centre node runs NetQASM: the primitives of primitives.py.

SquidASM's QNodeOS hands every instruction of a vanilla NetQASM subroutine
to an executor. This one turns each into the physical instructions the
NetSquid emulator uses for the same gate:

* data qubits go on the nuclear spins, and on the electron only once those
  are full, which leaves the electron free for entanglement;
* a gate the nuclear spins lack is rebuilt from the ones they have (``Z`` as
  a Z rotation, a Y rotation from X and Z rotations);
* a CNOT is ``ROT_X(t, -pi/2) CXDIR(e, t, pi/2) ROT_Z(e, -pi/2)``, with the
  control swapped onto the electron when it sits on a nuclear spin (CNOT in
  primitives.py), and conjugated by Hadamards when the target is the
  electron; a CZ is a CNOT between Hadamards on the nuclear spin;
* a nuclear spin is measured by swapping it onto the electron, reading the
  electron with the device's readout error and swapping back (Measure in
  primitives.py) -- SquidASM's own executors measure without readout error;
* before a pair is created or received, a qubit the electron still holds is
  swapped to a free nuclear spin, since only the electron can be entangled.
"""
from __future__ import annotations

from types import GeneratorType
from typing import Generator

import numpy as np
from netqasm.lang.instr import core, vanilla
from netsquid.components.instructions import (
    INSTR_CXDIR, INSTR_H, INSTR_INIT, INSTR_MEASURE, INSTR_ROT_X, INSTR_ROT_Y,
    INSTR_ROT_Z, INSTR_SWAP, INSTR_X, INSTR_Y, INSTR_Z,
)
from netsquid.components.qprogram import QuantumProgram
from pydynaa import EventExpression
from squidasm.nqasm.executor.vanilla import VanillaNetSquidExecutor

from netqmpi_colorcenters.device import ELECTRON


class ColorCenterExecutor(VanillaNetSquidExecutor):
    """Executor of vanilla NetQASM on a colour-centre processor."""

    def _get_unused_physical_qubit(self) -> int:
        for position in [*range(1, self.qdevice.num_positions), ELECTRON]:
            if position not in self._used_physical_qubit_addresses:
                self._used_physical_qubit_addresses.add(position)
                return position
        raise RuntimeError("No more qubits left in qdevice")

    def _clear_phys_qubit_in_memory(self, physical_address: int) -> None:
        # SquidASM frees a position by lowering its in_use flag and leaves the
        # freed qubit in it. This executor moves qubits through the electron:
        # measuring a nuclear spin swaps it there and back, and so does a CNOT
        # between two nuclear spins. Swapping a leftover qubit into the
        # electron raises the electron's in_use flag again, so the link layer
        # takes it for busy and waits forever for it to be freed: a telegate
        # hung on its second shot. Remove the freed qubit, so that a free
        # position is an empty one.
        if self.qdevice.peek(physical_address)[0] is not None:
            self.qdevice.discard(physical_address)
        super()._clear_phys_qubit_in_memory(physical_address)

    def _run(self, program: QuantumProgram) -> Generator[EventExpression, None, None]:
        if self.qdevice.busy:
            yield EventExpression(source=self.qdevice, event_type=self.qdevice.evtype_program_done)
        self.qdevice.execute_program(program)
        yield EventExpression(source=self.qdevice, event_type=self.qdevice.evtype_program_done)

    def _do_wait(self) -> Generator[EventExpression, None, None]:
        # SquidASM checks for a pending pair every microsecond. A pair over
        # a colour-centre link takes seconds -- millions of wake-ups -- and
        # arrives with an event of its own, so waking at the next event on
        # the timeline is enough.
        yield self._sleeper.sleep(sleep_ns=1e3)

    def _do_single_qubit_instr(self, instr, subroutine_id: int, address: int):
        position = self._get_position(subroutine_id=subroutine_id, address=address)
        on_carbon = position != ELECTRON
        program = QuantumProgram()
        if isinstance(instr, core.InitInstruction):
            program.apply(INSTR_INIT, [position])
        elif isinstance(instr, vanilla.GateXInstruction):
            program.apply(INSTR_X, [position])
        elif isinstance(instr, vanilla.GateHInstruction):
            program.apply(INSTR_H, [position])
        elif isinstance(instr, vanilla.GateZInstruction):
            if on_carbon:
                program.apply(INSTR_ROT_Z, [position], angle=np.pi)
            else:
                program.apply(INSTR_Z, [position])
        elif isinstance(instr, vanilla.GateYInstruction):
            if on_carbon:  # Y = iXZ
                program.apply(INSTR_ROT_Z, [position], angle=np.pi)
                program.apply(INSTR_X, [position])
            else:
                program.apply(INSTR_Y, [position])
        elif isinstance(instr, vanilla.GateSInstruction):
            program.apply(INSTR_ROT_Z, [position], angle=np.pi / 2)
        elif isinstance(instr, vanilla.GateTInstruction):
            program.apply(INSTR_ROT_Z, [position], angle=np.pi / 4)
        else:
            raise RuntimeError(f"{instr} is not supported on a colour-centre node")
        yield from self._run(program)

    def _do_single_qubit_rotation(self, instr, subroutine_id: int, address: int, angle: float):
        position = self._get_position(subroutine_id=subroutine_id, address=address)
        program = QuantumProgram()
        if isinstance(instr, vanilla.RotXInstruction):
            program.apply(INSTR_ROT_X, [position], angle=angle)
        elif isinstance(instr, vanilla.RotZInstruction):
            program.apply(INSTR_ROT_Z, [position], angle=angle)
        elif isinstance(instr, vanilla.RotYInstruction):
            if position == ELECTRON:
                program.apply(INSTR_ROT_Y, [position], angle=angle)
            else:  # Ry(a) = Rz(pi/2) Rx(a) Rz(-pi/2)
                program.apply(INSTR_ROT_Z, [position], angle=-np.pi / 2)
                program.apply(INSTR_ROT_X, [position], angle=angle)
                program.apply(INSTR_ROT_Z, [position], angle=np.pi / 2)
        else:
            raise RuntimeError(f"{instr} is not supported on a colour-centre node")
        yield from self._run(program)

    def _do_two_qubit_instr(self, instr, subroutine_id: int, address1: int, address2: int):
        first, second = self._get_positions(subroutine_id=subroutine_id,
                                             addresses=[address1, address2])
        program = QuantumProgram()
        if isinstance(instr, vanilla.CnotInstruction):
            _cnot(program, control=first, target=second)
        elif isinstance(instr, vanilla.CphaseInstruction):
            # CZ is symmetric: put the Hadamards on a nuclear spin.
            control, target = (first, second) if second != ELECTRON else (second, first)
            program.apply(INSTR_H, [target])
            _cnot(program, control, target)
            program.apply(INSTR_H, [target])
        else:
            raise RuntimeError(f"{instr} is not supported on a colour-centre node")
        yield from self._run(program)

    def _do_create_epr(self, subroutine_id: int, **kwargs):
        yield from self._free_electron()
        output = super()._do_create_epr(subroutine_id, **kwargs)
        if isinstance(output, GeneratorType):
            yield from output

    def _do_recv_epr(self, subroutine_id: int, **kwargs):
        yield from self._free_electron()
        output = super()._do_recv_epr(subroutine_id, **kwargs)
        if isinstance(output, GeneratorType):
            yield from output

    def _free_electron(self) -> Generator[EventExpression, None, None]:
        """Swap the qubit the electron holds, if any, to a free nuclear spin."""
        if ELECTRON not in self._used_physical_qubit_addresses:
            return
        free = [position for position in range(1, self.qdevice.num_positions)
                if position not in self._used_physical_qubit_addresses]
        if not free:
            raise RuntimeError(
                "Cannot entangle: the electron holds a qubit and every nuclear spin "
                "is taken, so there is nowhere to move it. Raise num_qubits.")
        carbon = free[0]
        program = QuantumProgram()
        program.apply(INSTR_SWAP, [ELECTRON, carbon])
        yield from self._run(program)

        for unit_module in self._qubit_unit_modules.values():
            for virtual, physical in enumerate(unit_module):
                if physical == ELECTRON:
                    unit_module[virtual] = carbon
        self._used_physical_qubit_addresses.discard(ELECTRON)
        self._used_physical_qubit_addresses.add(carbon)
        self._clear_phys_qubit_in_memory(ELECTRON)
        self._reserve_physical_qubit(carbon)

    def _meas_physical_qubit(self, position: int) -> Generator[EventExpression, None, int]:
        program = QuantumProgram()
        if position != ELECTRON:
            program.apply(INSTR_SWAP, [ELECTRON, position])
        program.apply(INSTR_MEASURE, [ELECTRON], output_key="outcome")
        if position != ELECTRON:
            program.apply(INSTR_SWAP, [ELECTRON, position])
        yield from self._run(program)
        return int(program.output["outcome"][0])


def _cnot(program: QuantumProgram, control: int, target: int) -> None:
    """Append a CNOT built on the electron-controlled CXDIR."""
    if control == ELECTRON:
        program.apply(INSTR_ROT_X, [target], angle=-np.pi / 2)
        program.apply(INSTR_CXDIR, [ELECTRON, target], angle=np.pi / 2)
        program.apply(INSTR_ROT_Z, [ELECTRON], angle=-np.pi / 2)
    elif target == ELECTRON:
        # CNOT(c, e) = (H x H) CNOT(e, c) (H x H)
        for position in (control, ELECTRON):
            program.apply(INSTR_H, [position])
        _cnot(program, ELECTRON, control)
        for position in (control, ELECTRON):
            program.apply(INSTR_H, [position])
    else:
        program.apply(INSTR_SWAP, [ELECTRON, control])
        program.apply(INSTR_ROT_X, [target], angle=-np.pi / 2)
        program.apply(INSTR_CXDIR, [ELECTRON, target], angle=np.pi / 2)
        program.apply(INSTR_SWAP, [ELECTRON, control])
        program.apply(INSTR_ROT_Z, [control], angle=-np.pi / 2)
