"""
Colour-centre QPUs for NetQMPI's NetQASM/SquidASM backend.

A NetQMPI simulation plugin with three entry points:

* ``nv_2026`` and ``snv_2026``: the NV and SnV platforms with the COMPUTAEX
  2026 parameters built in (``presets/``). Their ``plugin_config`` holds only
  overrides::

      netqasm:
        formalism: dm
        num_qubits: 3                    # electron + 2 nuclear spins
        plugin: netqmpi_colorcenters:nv_2026
        plugin_config:                   # optional
          device: {electron_T2: 2.0e+9}  # override single values
          link: null                     # NetQMPI's own links instead

* ``simulation``: the same model with every parameter given in
  ``plugin_config`` (a ``device`` and an optional ``link`` block), for a
  platform of your own.

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
from typing import Any, Dict, Iterator, Mapping, Optional

import yaml
from netqasm.lang.instr.flavour import VanillaFlavour
from squidasm.nqasm.qnodeos import SubroutineHandler
from squidasm.sim.network import network

from netqmpi_colorcenters.device import ELECTRON, build_qdevice
from netqmpi_colorcenters.executor import ColorCenterExecutor
from netqmpi_colorcenters.link import ElectronLinkLayer, build_distributor
from netqmpi_colorcenters.parameters import DeviceParameters, LinkParameters

__all__ = ["simulation", "nv_2026", "snv_2026", "Preset", "load_preset",
           "DeviceParameters", "LinkParameters", "ELECTRON"]

_BLOCKS = ("device", "link")


def simulation(config: Mapping[str, Any]):
    """
    The plugin with every parameter given in ``plugin_config``.

    Args:
        config: ``plugin_config`` of the config file, with a ``device`` and
            an optional ``link`` block.

    Returns:
        A context manager that makes SquidASM build colour-centre nodes.

    Raises:
        ValueError: On a block or parameter this plugin does not know.
    """
    unknown = set(config) - set(_BLOCKS)
    if unknown:
        raise ValueError(f"Unknown plugin_config blocks {sorted(unknown)}; "
                         "expected 'device' and optionally 'link'.")
    device = DeviceParameters.from_dict(config.get("device") or {})
    link = LinkParameters.from_dict(config["link"]) if config.get("link") is not None else None
    return _patches(device, link)


def load_preset(name: str) -> Dict[str, Any]:
    """
    Read a parameter set shipped in ``presets/``.

    Args:
        name: File name without extension, e.g. ``"nv_2026"``.

    Returns:
        A fresh ``plugin_config`` mapping for :func:`simulation`.
    """
    text = (resources.files(__package__) / "presets" / f"{name}.yaml").read_text()
    return yaml.safe_load(text)


class Preset:
    """
    A characterised platform: :func:`simulation` with a parameter set built in.

    Called with ``plugin_config``, which overrides the preset block by block:
    a key inside ``device`` or ``link`` replaces that value, and
    ``link: null`` drops the heralded link so NetQMPI's own links are used.

    Attributes:
        name: Name of the parameter set in ``presets/``.
        run_defaults: NetQASM run settings this platform was characterised
            with. NetQMPI does not read them yet; they are the defaults a
            plugin would declare under NetQIR/netqmpi#29. Until then, set
            them in the ``netqasm`` block of the config file.
    """

    run_defaults: Mapping[str, Any] = {"formalism": "dm", "num_qubits": 3}

    def __init__(self, name: str) -> None:
        self.name = name

    def parameters(self, overrides: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """
        The full ``plugin_config`` of :func:`simulation`: preset plus overrides.

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

    def __call__(self, config: Mapping[str, Any]):
        return simulation(self.parameters(config))

    def __repr__(self) -> str:
        return f"Preset({self.name!r})"


#: NV centres, NVParameterSet2026COMPUTAEX.
nv_2026 = Preset("nv_2026")
#: SnV centres, SnVParameterSet2026COMPUTAEX.
snv_2026 = Preset("snv_2026")


@contextmanager
def _patches(device: DeviceParameters, link: Optional[LinkParameters]) -> Iterator[None]:
    original_qdevice = network.QDevice
    original_link_layer = network.MagicNetworkLayerProtocol
    original_distributor = network.NetSquidNetwork.__dict__["_create_link_distributor"]
    original_executor = SubroutineHandler.__dict__["_get_executor_class"]

    def qdevice(name: str = "QDevice", num_qubits: int = 5, **_):
        return build_qdevice(name, num_qubits, device)

    def distributor(self, link_config, state_delay=None):
        nodes = [self.get_node(link_config.node_name1), self.get_node(link_config.node_name2)]
        return build_distributor(nodes, link)

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
        yield
    finally:
        network.QDevice = original_qdevice
        network.MagicNetworkLayerProtocol = original_link_layer
        network.NetSquidNetwork._create_link_distributor = original_distributor
        SubroutineHandler._get_executor_class = original_executor
