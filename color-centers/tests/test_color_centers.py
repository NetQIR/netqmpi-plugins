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


def _installed(name):
    from netqmpi import plugins
    return any(p.name == name and p.distribution == "netqmpi-colorcenters"
               for p in plugins.installed())
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
    run_app.metrics = captured[-1].comm.metrics if captured else {}
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
    if not _installed(name):
        pytest.skip("needs the package installed (pip install -e .) for its entry points")
    config = NetQASMRunConfig.from_dict(
        read_config_block(str(EXAMPLES / f"{name}.yaml"), "netqasm"))
    assert config.plugin == name
    assert config.plugin_config is None
    # Not set in the file: they come from the preset's run_defaults.
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
# The NetQMPI plugin protocol: run_defaults, configure, backends
# ----------------------------------------------------------------------

needs_install = pytest.mark.skipif(
    not _installed("nv_2026"),
    reason="needs the package installed (pip install -e .) for its entry points")


@needs_install
@pytest.mark.parametrize("name", ["nv_2026", "snv_2026"])
def test_a_short_name_brings_the_platform_run_settings(name):
    config = NetQASMRunConfig.from_dict({"plugin": name})
    assert config.formalism.value == "dm"
    assert config.num_qubits == 3


@needs_install
def test_the_user_still_overrides_run_defaults():
    assert NetQASMRunConfig.from_dict({"plugin": "nv_2026", "num_qubits": 5}).num_qubits == 5


def test_every_entry_point_declares_the_netqasm_backend():
    for plugin in (color_centers.simulation, color_centers.nv_2026, color_centers.snv_2026):
        assert plugin.backends == ("netqasm",)


@pytest.mark.parametrize("settings, match", [
    ({"hardware": "nv"}, "hardware"),
    ({"formalism": "stab"}, "stab"),
    ({"t1": 1e9}, "t1/t2"),
    ({"gate_fidelity": 0.99}, "gate_fidelity"),
    ({"link_fidelity": 0.9}, "link_fidelity"),
    ({"plugin_config": {"device": {"electron_t2": 1.0}}}, "electron_t2"),
])
def test_configure_refuses_what_the_plugin_would_ignore(settings, match):
    with pytest.raises(ValueError, match=match):
        NetQASMRunConfig(**{"plugin": "netqmpi_colorcenters:nv_2026", **settings})


def test_link_fidelity_is_fine_without_the_heralded_link():
    config = NetQASMRunConfig(plugin="netqmpi_colorcenters:nv_2026", link_fidelity=0.9,
                              plugin_config={"link": None})
    assert config.link_fidelity == 0.9


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


# ----------------------------------------------------------------------
# Telegates: expose/unexpose on colour centres
# ----------------------------------------------------------------------

#: A perfect heralded link: no loss, no dark counts, perfect visibility.
IDEAL_LINK = {"length": 1.0, "photon_emission_delay": 1e3}
LINKS = pytest.mark.parametrize("link_block", [None, IDEAL_LINK],
                                ids=["NetQMPI link", "heralded link"])

REMOTE_CNOT = """
    def main(env):
        comm = env.comm
        with comm:
            circuit = env.create_circuit(num_qubits=1, num_clbits=1)
            if comm.rank == 0 and {control}:
                circuit.x(0)
            if comm.rank == 1 and {target}:
                circuit.x(0)
            control = comm.expose(circuit, 0, [1], root=0)
            if comm.rank == 1:
                circuit.cx(control, 0)
            comm.unexpose(circuit, [1], root=0)
            circuit.measure(0, 0)
"""


@LINKS
@pytest.mark.parametrize("control, target", [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_a_telegate_is_a_remote_cnot(control, target, link_block, tmp_path):
    # The exposed control sits on the receiver's electron, its target on a
    # nuclear spin; on the root the pair's half is the electron and the data
    # qubit a nuclear spin, so both CNOT decompositions are exercised.
    source = REMOTE_CNOT.format(control=control, target=target)
    results = run_app(source, 2, tmp_path, link_block=link_block)
    assert results[0] == {str(control): SHOTS}
    assert results[1] == {str(control ^ target): SHOTS}


PHASE_KICKBACK = """
    def main(env):
        comm = env.comm
        with comm:
            circuit = env.create_circuit(num_qubits=1, num_clbits=1)
            if comm.rank == 0:
                circuit.h(0)                     # |+>
            control = comm.expose(circuit, 0, [1], root=0)
            if comm.rank == 1:
                circuit.cz(control, 0)           # target |0>: no effect
            comm.unexpose(circuit, [1], root=0)
            if comm.rank == 0:
                circuit.h(0)                     # |+> -> 0, |-> -> 1
            circuit.measure(0, 0)
"""


@LINKS
def test_unexpose_gives_the_control_back_with_its_phase(link_block, tmp_path):
    # The receiver's X-basis outcome is random; only the root's Z correction
    # makes the control |+> again, so a missing or wrong correction reads 1
    # in about half the shots.
    results = run_app(PHASE_KICKBACK, 2, tmp_path, link_block=link_block)
    assert results[0] == {"0": SHOTS}


FAN_OUT = """
    def main(env):
        comm = env.comm
        with comm:
            circuit = env.create_circuit(num_qubits=1, num_clbits=1)
            if comm.rank == 0:
                circuit.x(0)
            control = comm.expose(circuit, 0, [1, 2], root=0)
            if comm.rank != 0:
                circuit.cx(control, 0)
            comm.unexpose(circuit, [1, 2], root=0)
            circuit.measure(0, 0)
"""


@LINKS
def test_one_root_exposes_to_two_receivers(link_block, tmp_path):
    results = run_app(FAN_OUT, 3, tmp_path, link_block=link_block)
    assert results == {0: {"1": SHOTS}, 1: {"1": SHOTS}, 2: {"1": SHOTS}}


def test_the_heralded_link_reports_its_pairs(tmp_path):
    # Two teleportations per shot over a perfect heralded link: every pair is
    # counted, and each is a perfect Bell state.
    run_app(TWO_TELEPORTS, 2, tmp_path, link_block=IDEAL_LINK)
    link_metrics = run_app.metrics["plugin"]
    assert link_metrics["epr_pairs"] == 2 * SHOTS
    assert link_metrics["epr_attempts"] >= link_metrics["epr_pairs"]
    assert link_metrics["pair_fidelity"] == pytest.approx(1.0)
    assert len(link_metrics["pair_time_ns"]) == 2 * SHOTS
    assert len(run_app.metrics["netqmpi"]["sim_time_ns"]) == SHOTS


def test_netqmpi_links_report_nothing_of_ours(tmp_path):
    run_app(TWO_TELEPORTS, 2, tmp_path)
    assert "plugin" not in run_app.metrics
