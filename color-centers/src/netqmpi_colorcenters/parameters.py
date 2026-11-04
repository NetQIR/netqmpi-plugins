"""
The two blocks of the plugin configuration: the device and the link.

Parameter names are those of the parameter sets in nv_2026.py and
snv_2026.py, so a set carries over to the config file key by key. Every
default is the perfect value, so a key left out adds no noise and no delay.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Type, TypeVar

_T = TypeVar("_T", bound="_Block")


class _Block:
    """Parsing shared by both blocks."""

    #: Name of the block in the config file, for error messages.
    NAME = ""
    #: Fields that are probabilities, checked to lie in [0, 1].
    PROBABILITIES: tuple = ()

    @classmethod
    def from_dict(cls: Type[_T], data: Mapping[str, Any]) -> _T:
        """
        Build the block from its mapping in the config file.

        Every value is converted to ``float``. That matters for YAML: PyYAML
        reads ``3.6e12`` (no sign in the exponent) as a string.

        Raises:
            ValueError: On an unknown key, a value that is not a number, a
                negative value, or a probability above 1.
        """
        names = {f.name for f in dataclasses.fields(cls)}
        unknown = set(data) - names
        if unknown:
            raise ValueError(f"Unknown {cls.NAME} parameters {sorted(unknown)}; "
                             f"expected some of {sorted(names)}.")
        values: Dict[str, float] = {}
        for key, value in data.items():
            try:
                values[key] = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"{cls.NAME}.{key} must be a number, got {value!r}. "
                                 "In YAML write exponents with a sign, e.g. 3.6e+12.") from None
            if values[key] < 0:
                raise ValueError(f"{cls.NAME}.{key} must not be negative, got {value}.")
            if key in cls.PROBABILITIES and values[key] > 1:
                raise ValueError(f"{cls.NAME}.{key} must be in [0, 1], got {value}.")
        block = cls(**values)
        block._verify()
        return block

    def _verify(self) -> None:
        pass


@dataclass
class DeviceParameters(_Block):
    """
    The colour centre: an electron spin and its nuclear spins.

    Times are in ns. Gate errors are the ``depolar_rate`` of a
    time-independent depolarising channel, ``(4/3)(1 - F)`` for a gate of
    fidelity ``F``. A coherence time of 0 disables that channel.
    """

    NAME = "device"
    PROBABILITIES = ("prob_error_0", "prob_error_1")

    electron_T1: float = 0.0
    electron_T2: float = 0.0
    carbon_T1: float = 0.0
    carbon_T2: float = 0.0

    electron_init_depolar_prob: float = 0.0
    electron_single_qubit_depolar_prob: float = 0.0
    carbon_init_depolar_prob: float = 0.0
    #: Applied to every carbon gate, H and X included, as in processors.py.
    carbon_z_rot_depolar_prob: float = 0.0
    ec_gate_depolar_prob: float = 0.0
    magical_swap_gate_depolar_prob: float = 0.0

    #: Probability that outcome 0 reads as 1, and 1 as 0.
    prob_error_0: float = 0.0
    prob_error_1: float = 0.0

    electron_init_duration: float = 0.0
    electron_single_qubit_duration: float = 0.0
    carbon_init_duration: float = 0.0
    carbon_z_rot_duration: float = 0.0
    #: Duration of the carbon H, X and X rotation.
    carbon_single_qubit_duration: float = 0.0
    ec_two_qubit_gate_duration: float = 0.0
    measure_duration: float = 0.0
    magical_swap_gate_duration: float = 0.0


@dataclass
class LinkParameters(_Block):
    """
    Heralded double-click entanglement between two electron spins.

    The model of entanglement.py: a midpoint station halfway along a fibre
    of ``length`` km, NetSquid-magic's double-click state model, and the
    dephasing every attempt induces on the nuclear spins of both nodes
    (netsquid-nv's ``NVDoubleClickMagicDistributor``).
    """

    NAME = "link"
    PROBABILITIES = ("emission_fidelity", "total_detection_eff", "prob_dark_count",
                     "visibility", "coin_prob_ph_ph", "coin_prob_ph_dc", "coin_prob_dc_dc")

    #: Total fibre length [km]; each node is length / 2 from the station.
    length: float = 0.0
    #: Speed of light in the fibre [km/s].
    c: float = 300000.0
    #: Fibre attenuation [dB/km].
    p_loss_lengths_with_conversion: float = 0.0
    #: Time to emit a photon entangled with the electron [ns].
    photon_emission_delay: float = 0.0
    emission_fidelity: float = 1.0
    #: Probability that an emitted photon is detected, fibre excluded.
    total_detection_eff: float = 1.0
    prob_dark_count: float = 0.0
    visibility: float = 1.0
    #: Delta_omega * tau_decay, which sets the nuclear dephasing per attempt.
    product_tau_decay_delta_w: float = 0.0
    #: Phase [rad] behind the dephasing applied once per round.
    initial_nuclear_phase: float = 0.0
    coin_prob_ph_ph: float = 1.0
    coin_prob_ph_dc: float = 1.0
    coin_prob_dc_dc: float = 1.0

    def _verify(self) -> None:
        if self.c <= 0:
            raise ValueError(f"link.c must be positive, got {self.c}.")
        if self.length == 0 and self.photon_emission_delay == 0:
            raise ValueError("An attempt would take no time: give link.length or "
                             "link.photon_emission_delay a positive value.")
