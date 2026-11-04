"""
Tests of the color_centers plugin, on NetQMPI's NetQASM backend.

Run from the plugin directory:  python -m pytest

The simulations use an ideal device or one with a single deliberate error,
so every outcome they check is certain.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytest.importorskip("squidasm", reason="the NetQASM backend needs SquidASM")
pytest.importorskip("netqmpi", reason="the plugin runs under NetQMPI")

from netqmpi.runtime.adapters.netqasm import NetQASMExecutorAdapter, NetQASMRunConfig  # noqa: E402
from netqmpi.runtime.run_config import read_config_block  # noqa: E402
from netqmpi.sdk.environment import Environment  # noqa: E402

import netqmpi_colorcenters as color_centers  # noqa: E402
from netqmpi_colorcenters import link  # noqa: E402

PLUGIN = "netqmpi_colorcenters:simulation"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
SHOTS = 3


def run_app(source, ranks, tmp_path, num_qubits=3, device=None, link_block=None):
    """Run a NetQMPI program on colour-centre nodes; one histogram per rank."""
    app = tmp_path / "app.py"
    app.write_text(textwrap.dedent(source))
    plugin_config = {"device": device or {}}
    if link_block is not None:
        plugin_config["link"] = link_block

    captured = []
    original = Environment.__init__

    def capture(self, comm, executor):
        original(self, comm, executor)
        captured.append(self)

    Environment.__init__ = capture
    try:
        config = NetQASMRunConfig(formalism="dm", shots=SHOTS, num_qubits=num_qubits,
                                  plugin=PLUGIN, plugin_config=plugin_config)
        executor = NetQASMExecutorAdapter(ranks, config)
        executor.run(executor.build_apps(str(app), ranks))
    finally:
        Environment.__init__ = original
    return {env.comm.rank: dict(env.comm.results)
            for env in sorted(captured, key=lambda e: e.comm.rank)}


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

@pytest.mark.parametrize("name", ["nv_2026", "snv_2026"])
def test_the_presets_load(name):
    block = color_centers.load_preset(name)
    assert color_centers.DeviceParameters.from_dict(block["device"]).carbon_T2 > 0
    assert color_centers.LinkParameters.from_dict(block["link"]).length == 1.0


@pytest.mark.parametrize("name", ["nv_2026", "snv_2026"])
def test_the_example_configs_select_the_presets(name):
    config = NetQASMRunConfig.from_dict(
        read_config_block(str(EXAMPLES / f"{name}.yaml"), "netqasm"))
    assert config.plugin == f"netqmpi_colorcenters:{name}"
    assert config.plugin_config is None
    # What the platform was characterised with, until NetQMPI reads
    # run_defaults itself (NetQIR/netqmpi#29).
    preset = getattr(color_centers, name)
    assert config.formalism.value == preset.run_defaults["formalism"]
    assert config.num_qubits == preset.run_defaults["num_qubits"]


def test_preset_overrides_replace_single_values():
    preset = color_centers.nv_2026
    merged = preset.parameters({"device": {"electron_T2": 2.0e9}})
    original = color_centers.load_preset("nv_2026")
    assert merged["device"]["electron_T2"] == 2.0e9
    assert merged["device"]["carbon_T2"] == original["device"]["carbon_T2"]
    assert merged["link"] == original["link"]


def test_preset_link_null_drops_the_heralded_link():
    assert color_centers.snv_2026.parameters({"link": None})["link"] is None


@pytest.mark.parametrize("overrides, match", [
    ({"device": {"carbon_t2": 1.0}}, "carbon_t2"),
    ({"devices": {}}, "devices"),
])
def test_bad_preset_overrides_are_refused(overrides, match):
    with pytest.raises(ValueError, match=match):
        color_centers.nv_2026(overrides)


def test_yaml_exponents_without_sign_still_read_as_numbers():
    # PyYAML reads 1.58e9 as the string "1.58e9".
    assert color_centers.DeviceParameters.from_dict({"electron_T2": "1.58e9"}).electron_T2 == 1.58e9


@pytest.mark.parametrize("block, match", [
    ({"device": {"carbon_t2": 1.0}}, "carbon_t2"),
    ({"device": {"measure_duration": "slow"}}, "measure_duration"),
    ({"device": {"prob_error_0": 2.0}}, "prob_error_0"),
    ({"link": {"length": 0.0}}, "no time"),
    ({"devices": {}}, "devices"),
])
def test_bad_plugin_config_is_refused(block, match):
    with pytest.raises(ValueError, match=match):
        color_centers.simulation(block)


# ----------------------------------------------------------------------
# Simulation
# ----------------------------------------------------------------------

#: Every gate the executor decomposes, arranged so the outcome is certain:
#: qubit 0 ends in |0>, qubit 1 in |1>, read as "01".
GATES = """
    import numpy as np

    def main(env):
        comm = env.comm
        with comm:
            circuit = env.create_circuit(num_qubits=2, num_clbits=2)
            circuit.x(0)                  # |10>
            circuit.cx(0, 1)              # |11>
            circuit.h(1)
            circuit.cz(0, 1)
            circuit.h(1)                  # HZH = X on qubit 1: |10>
            circuit.ry(np.pi, 1)          # |11>
            circuit.s(0)
            circuit.t(0)
            circuit.t(0)
            circuit.z(0)                  # S T T Z = identity up to phase
            circuit.cx(1, 0)              # |01>
            circuit.y(1)
            circuit.rx(np.pi, 1)          # Rx(pi) Y = identity up to phase
            circuit.rz(np.pi / 2, 0)
            circuit.measure(0, 1)
            circuit.measure(1, 0)
"""


@pytest.mark.parametrize("num_qubits", [2, 3], ids=["carbon+electron", "two carbons"])
def test_gates_decompose_into_the_same_operation(num_qubits, tmp_path):
    # Two positions put the second qubit on the electron (electron-controlled
    # and electron-targeted CNOTs); three keep both on nuclear spins (CNOT
    # through the SWAP gate).
    assert run_app(GATES, 1, tmp_path, num_qubits=num_qubits)[0] == {"01": SHOTS}


READ_ZERO = """
    def main(env):
        comm = env.comm
        with comm:
            circuit = env.create_circuit(num_qubits=1, num_clbits=1)
            circuit.measure(0, 0)
"""


def test_the_readout_error_is_applied(tmp_path):
    # With prob_error_0 = 1 a |0> always reads 1; SquidASM's own executors
    # measure without readout error and would read 0.
    results = run_app(READ_ZERO, 1, tmp_path, num_qubits=2, device={"prob_error_0": 1.0})
    assert results[0] == {"1": SHOTS}


TWO_TELEPORTS = """
    def main(env):
        comm = env.comm
        with comm:
            circuit = env.create_circuit(num_qubits=2, num_clbits=2)
            if comm.rank == 0:
                circuit.x(0)
                circuit.x(1)
                comm.qsend(circuit, [0], 1)
                comm.qsend(circuit, [1], 1)
            else:
                comm.qrecv(circuit, [0], 0)
                comm.qrecv(circuit, [1], 0)
                circuit.measure(0, 0)
                circuit.measure(1, 1)
"""


@pytest.mark.parametrize("link_block", [None, {"length": 1.0, "photon_emission_delay": 1e3}],
                         ids=["NetQMPI link", "heralded link"])
def test_only_electrons_are_entangled(link_block, tmp_path, monkeypatch):
    # The receiver still holds the first qubit on its electron when the
    # second pair is due: it must move it to a nuclear spin, not let the pair
    # land on one.
    delivered = []
    original = link.ElectronLinkLayer._get_unused_memory_positions

    def spy(self):
        positions = original(self)
        if positions is not None:
            delivered.extend(positions.values())
        return positions

    monkeypatch.setattr(link.ElectronLinkLayer, "_get_unused_memory_positions", spy)
    results = run_app(TWO_TELEPORTS, 2, tmp_path, link_block=link_block)

    assert results[1] == {"11": SHOTS}
    assert delivered and set(delivered) == {color_centers.ELECTRON}
