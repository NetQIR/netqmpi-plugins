"""
Colour-centre QPUs for NetQMPI's NetQASM/SquidASM backend.

A NetQMPI simulation plugin with three entry points, registered in the
``netqmpi.plugins`` group:

* ``nv_2026`` and ``snv_2026``: the NV and SnV platforms with the COMPUTAEX
  2026 parameters built in (``presets/``). They set the run settings they
  were characterised with (``run_defaults``), and their ``plugin_config``
  holds only overrides::

      netqmpi -n 2 app.py --netqasm --plugin nv_2026

      netqasm:                           # or, in a config file
        plugin: nv_2026
        plugin_config:                   # optional
          device: {electron_T2: 2.0e+9}  # override single values
          link: null                     # NetQMPI's own links instead

* ``color_centers``: the same model with every parameter given in
  ``plugin_config`` (a ``device`` and an optional ``link`` block), for a
  platform of your own.

Each follows NetQMPI's plugin protocol: ``backends`` (NetQASM only),
``run_defaults``, and ``configure``, which refuses settings of the
``netqasm`` block the plugin would ignore. With a heralded link, the context
manager yields a :class:`~netqmpi_plugins.colorcenters.link.LinkStats`, so the run
reports its pairs in ``comm.metrics["plugin"]``.

SquidASM has no hook for a device, an executor or a link of its own, so the
plugin swaps the names SquidASM builds them from for the length of the run:

* every node gets the processor of :mod:`.device` and the executor of
  :mod:`.executor`;
* the link layer only entangles electrons (:mod:`.link`);
* with a ``link`` block, every link is a heralded double-click link
  (:mod:`.link`).
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from importlib import resources
from typing import Any, Dict, Iterator, Mapping, Optional, Tuple

import yaml

try:
    import netsquid  # noqa: F401
    import netsquid_magic  # noqa: F401
    import squidasm  # noqa: F401
except ImportError as error:  # pragma: no cover - depends on the environment
    raise ImportError(
        f"the colorcenters plugin needs SquidASM, NetSquid and netsquid-magic ({error}). "
        "Install them with: pip install 'netqmpi-plugins[colorcenters]' "
        "--extra-index-url https://pypi.netsquid.org") from error

from netqasm.lang.instr.flavour import VanillaFlavour
from squidasm.nqasm.qnodeos import SubroutineHandler
from squidasm.sim.network import network

from netqmpi_plugins.colorcenters.device import ELECTRON, build_qdevice
from netqmpi_plugins.colorcenters.executor import ColorCenterExecutor
from netqmpi_plugins.colorcenters.link import ElectronLinkLayer, LinkStats, build_distributor
from netqmpi_plugins.colorcenters.parameters import DeviceParameters, LinkParameters

__all__ = ["simulation", "nv_2026", "snv_2026", "ColorCenters", "Preset", "load_preset",
           "DeviceParameters", "LinkParameters", "LinkStats", "ELECTRON"]

_BLOCKS = ("device", "link")


def load_preset(name: str) -> Dict[str, Any]:
    """
    Read a parameter set shipped in ``presets/``.

    Args:
        name: File name without extension, e.g. ``"nv_2026"``.

    Returns:
        A fresh ``plugin_config`` mapping for :data:`simulation`.
    """
    text = (resources.files(__package__) / "presets" / f"{name}.yaml").read_text()
    return yaml.safe_load(text)


class ColorCenters:
    """
    The plugin with every parameter given in ``plugin_config``.

    ``plugin_config`` holds a ``device`` block and an optional ``link``
    block; without ``link``, NetQMPI's own links deliver the pairs. Follows
    NetQMPI's plugin protocol (``netqmpi.plugins.Plugin``).
    """

    backends = ("netqasm",)
    #: Mixed states (heralded pairs, depolarising gates) need density matrices.
    run_defaults: Mapping[str, Any] = {"formalism": "dm"}

    def parameters(self, config: Mapping[str, Any]) -> Dict[str, Any]:
        """The full ``device``/``link`` mapping this plugin runs with."""
        unknown = set(config) - set(_BLOCKS)
        if unknown:
            raise ValueError(f"Unknown plugin_config blocks {sorted(unknown)}; "
                             "expected 'device' and optionally 'link'.")
        return dict(config)

    def build(self, config: Mapping[str, Any]) -> Tuple[DeviceParameters, Optional[LinkParameters]]:
        """
        Parse ``plugin_config`` into the device and link parameters.

        Raises:
            ValueError: On a block or parameter this plugin does not know.
        """
        full = self.parameters(config)
        device = DeviceParameters.from_dict(full.get("device") or {})
        link = LinkParameters.from_dict(full["link"]) if full.get("link") is not None else None
        return device, link

    def configure(self, plugin_config: Mapping[str, Any], run_config: Any) -> None:
        """
        Check the parameters and the run config, before any rank is traced.

        Refuses settings of the ``netqasm`` block this plugin would ignore
        or cannot honour, rather than letting them be ignored in silence.
        """
        _, link = self.build(plugin_config)
        _check_run_config(run_config, link)

    def __call__(self, config: Mapping[str, Any]):
        """Return the context manager that makes SquidASM build colour-centre nodes."""
        return _patches(*self.build(config))

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"


class Preset(ColorCenters):
    """
    A characterised platform: :class:`ColorCenters` with a parameter set built in.

    ``plugin_config`` overrides the preset block by block: a key inside
    ``device`` or ``link`` replaces that value, and ``link: null`` drops the
    heralded link so NetQMPI's own links are used.

    Attributes:
        name: Name of the parameter set in ``presets/``.
    """

    #: The run settings the platform was characterised with: density
    #: matrices, and an electron plus two nuclear spins (Processor2026(3)).
    run_defaults: Mapping[str, Any] = {"formalism": "dm", "num_qubits": 3}

    def __init__(self, name: str) -> None:
        self.name = name

    def parameters(self, overrides: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """
        The full ``plugin_config`` of :class:`ColorCenters`: preset plus overrides.

        Raises:
            ValueError: On an override block this plugin does not know.
        """
        overrides = overrides or {}
        unknown = set(overrides) - set(_BLOCKS)
        if unknown:
            raise ValueError(f"Unknown plugin_config blocks {sorted(unknown)} for preset "
                             f"{self.name!r}; expected overrides of 'device' and 'link'.")
        merged = load_preset(self.name)
        for block in _BLOCKS:
            if block not in overrides:
                continue
            if overrides[block] is None:
                merged[block] = None
            else:
                merged[block] = {**(merged.get(block) or {}), **copy.deepcopy(overrides[block])}
        return merged

    def __repr__(self) -> str:
        return f"Preset({self.name!r})"


#: Every parameter in plugin_config (entry point ``color_centers``).
simulation = ColorCenters()
#: NV centres, NVParameterSet2026COMPUTAEX.
nv_2026 = Preset("nv_2026")
#: SnV centres, SnVParameterSet2026COMPUTAEX.
snv_2026 = Preset("snv_2026")


def _check_run_config(run_config: Any, link: Optional[LinkParameters]) -> None:
    """Refuse netqasm-block settings the plugin would ignore or cannot honour."""
    problems = []
    if getattr(run_config, "hardware", "generic") != "generic":
        problems.append(
            f"hardware is {run_config.hardware!r}: SquidASM builds those nodes with a "
            "device of its own, which this plugin does not replace. Leave it 'generic'.")
    formalism = getattr(getattr(run_config, "formalism", None), "value", None)
    if formalism == "stab":
        problems.append("formalism 'stab' cannot hold the mixed states of noisy colour "
                        "centres; use 'dm'.")
    if getattr(run_config, "t1", 0) or getattr(run_config, "t2", 0):
        problems.append("t1/t2 would be ignored: memory decoherence comes from "
                        "device.electron_T1/T2 and device.carbon_T1/T2 in plugin_config.")
    if getattr(run_config, "gate_fidelity", 1.0) != 1.0:
        problems.append("gate_fidelity would be ignored: each instruction's noise comes "
                        "from the device block of plugin_config.")
    if link is not None and getattr(run_config, "link_fidelity", 1.0) != 1.0:
        problems.append("link_fidelity would be ignored: pairs come from the heralded "
                        "link. Drop it, or set 'link: null' to use NetQMPI's links.")
    if problems:
        raise ValueError("colour-centre plugin: " + " ".join(problems))


@contextmanager
def _patches(device: DeviceParameters,
             link: Optional[LinkParameters]) -> Iterator[Optional[LinkStats]]:
    original_qdevice = network.QDevice
    original_link_layer = network.MagicNetworkLayerProtocol
    original_distributor = network.NetSquidNetwork.__dict__["_create_link_distributor"]
    original_executor = SubroutineHandler.__dict__["_get_executor_class"]

    def qdevice(name: str = "QDevice", num_qubits: int = 5, **_):
        return build_qdevice(name, num_qubits, device)

    stats = LinkStats() if link is not None else None

    def distributor(self, link_config, state_delay=None):
        nodes = [self.get_node(link_config.node_name1), self.get_node(link_config.node_name2)]
        return build_distributor(nodes, link, stats)

    def executor_class(cls, flavour=None):
        if flavour is None or isinstance(flavour, VanillaFlavour):
            return ColorCenterExecutor
        return original_executor.__func__(cls, flavour)

    network.QDevice = qdevice
    network.MagicNetworkLayerProtocol = ElectronLinkLayer
    if link is not None:
        network.NetSquidNetwork._create_link_distributor = distributor
    SubroutineHandler._get_executor_class = classmethod(executor_class)
    try:
        # NetQMPI reads stats.report() into comm.metrics["plugin"] after the
        # run; with NetQMPI's own links there is nothing of ours to report.
        yield stats
    finally:
        network.QDevice = original_qdevice
        network.MagicNetworkLayerProtocol = original_link_layer
        network.NetSquidNetwork._create_link_distributor = original_distributor
        SubroutineHandler._get_executor_class = original_executor
