# netqmpi-colorcenters

NV and SnV colour-centre QPUs with heralded double-click links, as a NetQMPI
simulation plugin for the NetQASM/SquidASM backend.

This plugin ports the NetSquid colour-centre emulator
[Diamond-color-centers-emulation-on-NetSquid](https://github.com/rodrigt11/Diamond-color-centers-emulation-on-NetSquid)
(COMPUTAEX). Its processor, gate primitives, entanglement model and 2026
parameter sets are rebuilt on SquidASM. File names below (`processors.py`,
`primitives.py`, `entanglement.py`, `nv_2026.py`, `snv_2026.py`) refer to
that repository.

```
color-centers/
├── src/netqmpi_colorcenters/
│   ├── __init__.py         # entry points: simulation, nv_2026, snv_2026
│   ├── parameters.py       # the device and link blocks of plugin_config
│   ├── device.py           # the processor: processors.py
│   ├── executor.py         # gate by gate: primitives.py
│   ├── link.py             # heralded double-click pairs: entanglement.py
│   └── presets/            # nv_2026.yaml, snv_2026.yaml
├── examples/
│   ├── dega.py             # DEGA.py (2-bit chunks), one rank per QPU
│   ├── teleport.py         # qsend/qrecv between two QPUs over the heralded link
│   ├── nv_2026.yaml
│   └── snv_2026.yaml
└── tests/
```

## Running

You need NetQMPI with plugin support (`main`, not in a release yet),
SquidASM 0.13.6 and NetQASM 2.0, all of which the `netqasm2` environment has:

```bash
conda activate netqasm2
pip install -e . --no-deps
netqmpi -n 2 examples/dega.py --netqasm --config examples/nv_2026.yaml
TELEPORT_STATE=+ netqmpi -n 2 examples/teleport.py --netqasm --config examples/snv_2026.yaml
python -m pytest
```

If you would rather not install it, prefix the commands with `PYTHONPATH=$PWD/src`.

SquidASM simulates the whole network once per shot, which takes about half a
second per shot with two ranks, even on NV, where each pair takes ~10 s of
simulated time. On this backend only the last rank gets its counts inside
`main`, so only that rank prints them.

## Entry points

| Entry point | `plugin_config` |
|---|---|
| `netqmpi_colorcenters:nv_2026` | Optional overrides of the NV preset (`NVParameterSet2026COMPUTAEX`) |
| `netqmpi_colorcenters:snv_2026` | Optional overrides of the SnV preset (`SnVParameterSet2026COMPUTAEX`) |
| `netqmpi_colorcenters:simulation` | Every parameter: a `device` block and an optional `link` block |

With a preset, an override replaces single values, and `link: null` drops the
heralded link so NetQMPI's own links are used:

```yaml
netqasm:
  formalism: dm          # what the platform was characterised with
  num_qubits: 3          # electron + 2 nuclear spins
  plugin: netqmpi_colorcenters:nv_2026
  plugin_config:
    device:
      electron_T2: 2.0e+9
```

NetQMPI cannot yet take `formalism` and `num_qubits` from the plugin, so set
them in the config file. Each preset records them in `run_defaults` for when
it can ([NetQIR/netqmpi#29](https://github.com/NetQIR/netqmpi/issues/29)).

Parameter keys have the same names as the attributes of the parameter sets in
`nv_2026.py` and `snv_2026.py`, and the presets copy their values exactly.
With `simulation`, any key you leave out takes its perfect value: no noise
and zero duration. In YAML, write exponents with a sign (`3.6e+12`).

## What is reproduced

- **Device** (`processors.py`):
  - The electron spin is at position 0 and the nuclear spins are at 1..n-1.
  - Each instruction has the same topology, the same depolarising noise and
    the same duration.
  - Memory decoherence is T1/T2.
  - Readout uses the POVM set by `prob_error_0`/`prob_error_1`.
  - The electron-nuclear SWAP is the magical one.
- **Gates** (`primitives.py`): each NetQMPI gate turns into the physical
  instructions the NetSquid primitives use.
  - A CNOT is `ROT_X`, `CXDIR`, `ROT_Z`, with the control swapped onto the
    electron when it is on a nuclear spin.
  - A nuclear spin is measured with SWAP, measure, SWAP.
  - Data qubits go on the nuclear spins.
  - Only the electron is entangled. If the electron still holds a qubit when
    the next pair is due, that qubit is first swapped to a free nuclear spin.
- **Link** (`entanglement.py`): the `Entangler`'s
  `NVDoubleClickMagicDistributor`.
  - It uses netsquid-magic's double-click state model with the same
    parameters: a 1 km fibre with the station in the middle, emission delay,
    emission fidelity, detection efficiency, dark counts and visibility.
  - After each pair, the nuclear spins of both nodes are dephased by
    `(1 - α)/2 (1 - exp(-(Δω τ)²/2))` per attempt (α = ½, applied twice), as
    netsquid-nv does.
  - As in the `Entangler`, the pair is corrected to Φ+ on node A's electron
    with physical X (and Z for Ψ−) instructions. NetQASM is not left to do
    it: NetQASM 2.0 always applies that correction to virtual qubit 0, so a
    node that already held a qubit would correct the wrong one.

netsquid-nv cannot be installed next to SquidASM: it needs netsquid-magic 13,
and SquidASM ships 16. So `link.py` rebuilds its distributor on
netsquid-magic 16, whose double-click model is the same.

## Checked against the NetSquid code

The original code was run unmodified (netsquid-magic 13.4.1, netsquid-nv
master) and compared with the plugin:

- **DEGA**: the gate and measurement instructions (44 per node) are identical
  to `DEGA.py`. The only difference is initialisation. `DEGA.py` resets the
  electron and both nuclear spins at the start; NetQMPI resets each nuclear
  spin just before its first gate. The success probabilities agree within
  sampling error.
- **Link**: compared with the distributor `Entangler` builds, for NV and SnV,
  these are equal to the last bit: success probability per attempt, cycle
  time, state and label delays, and the delivered states and their
  probabilities. The nuclear dephasing agrees to 1e-14.
- **Teleportation**: `teleport.py` was compared with the same protocol
  written in NetSquid on the `Entangler` and `processors.py`. The comparison
  covered |1⟩ and |+⟩, NV and SnV, plus variants that switch on one link
  noise source at a time. The probability of arriving intact and the number
  of attempts per pair agree within sampling error.

## Not yet covered

- **Arbitrary angles.** NetQASM encodes a rotation as n·π/2^d. Multiples of
  π/4 are exact, but any other angle (for example the phases of `Long`,
  DEGGA, or DEGA with 3-bit chunks) is split into several rotations, and each
  one adds gate noise and time.
- **Remote gates (`telegate.py`).** NetQMPI's `expose`/`unexpose` are not
  implemented on the NetQASM backend yet
  ([NetQIR/netqmpi#31](https://github.com/NetQIR/netqmpi/issues/31)).
