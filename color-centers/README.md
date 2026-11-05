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
│   ├── __init__.py         # entry points: nv_2026, snv_2026, color_centers
│   ├── parameters.py       # the device and link blocks of plugin_config
│   ├── device.py           # the processor: processors.py
│   ├── executor.py         # gate by gate: primitives.py
│   ├── link.py             # heralded double-click pairs: entanglement.py
│   └── presets/            # nv_2026.yaml, snv_2026.yaml
├── examples/
│   ├── dega.py             # DEGA.py (2-bit chunks), one rank per QPU
│   ├── teleport.py         # qsend/qrecv between two QPUs over the heralded link
│   ├── telegate.py         # remote CNOT with expose/unexpose, plus link metrics
│   ├── nv_2026.yaml        # optional config files: shots and overrides
│   └── snv_2026.yaml
└── tests/
```

## Running

You need NetQMPI `main` with plugin support (not in a release yet), SquidASM
0.13.6 and NetQASM 2.0, all of which the `netqasm2` environment has. Install
the plugin so NetQMPI finds it by name, from any directory:

```bash
conda activate netqasm2
pip install -e . --no-deps
netqmpi --list-plugins

netqmpi -n 2 examples/dega.py --netqasm --plugin nv_2026
TELEPORT_STATE=+ netqmpi -n 2 examples/teleport.py --netqasm --plugin snv_2026
netqmpi -n 2 examples/telegate.py --netqasm --plugin nv_2026 --metrics metrics.json
python -m pytest
```

SquidASM simulates the whole network once per shot, which takes about half a
second per shot with two ranks. That holds even on NV, where a pair takes
~1.6 million attempts, about 20 s of simulated time. On this backend only the
last rank gets its counts and metrics inside `main`, so only that rank prints
them.

## Entry points

| Short name | Target | `plugin_config` |
|---|---|---|
| `nv_2026` | `netqmpi_colorcenters:nv_2026` | Optional overrides of the NV preset (`NVParameterSet2026COMPUTAEX`) |
| `snv_2026` | `netqmpi_colorcenters:snv_2026` | Optional overrides of the SnV preset (`SnVParameterSet2026COMPUTAEX`) |
| `color_centers` | `netqmpi_colorcenters:simulation` | Every parameter: a `device` block and an optional `link` block |

The presets set the run settings the platform was characterised with
(`run_defaults`): `formalism: dm`, and `num_qubits: 3`, an electron and two
nuclear spins. `color_centers` sets only `formalism: dm`. Anything in the
config file or on the command line still wins.

With a preset, an override replaces single values, and `link: null` drops the
heralded link so NetQMPI's own links are used. Pass the overrides with
`--plugin-config FILE`, or in the config file:

```yaml
netqasm:
  plugin: nv_2026
  plugin_config:
    device:
      electron_T2: 2.0e+9
```

Parameter keys have the same names as the attributes of the parameter sets in
`nv_2026.py` and `snv_2026.py`, and the presets copy their values exactly.
With `color_centers`, any key you leave out takes its perfect value: no noise
and zero duration. In YAML, write exponents with a sign (`3.6e+12`).

### Checks before the run

The plugin's `configure` refuses, before any rank is traced:

- a typo or a bad value in `plugin_config`;
- `hardware` other than `generic`, because SquidASM builds those nodes with a
  device of its own that the plugin does not replace;
- `formalism: stab`, which cannot hold the mixed states of noisy colour
  centres;
- `t1`, `t2` or `gate_fidelity`, which would be ignored because the noise
  comes from the `device` block;
- `link_fidelity` together with the heralded link, which would also be
  ignored.

It runs on the NetQASM backend only; `--aer --plugin nv_2026` is refused.

### Metrics

With the heralded link, the plugin reports what the links delivered in
`comm.metrics["plugin"]`, which `--metrics FILE` writes to JSON. The counts
cover every link and every shot of the run:

| Key | Meaning |
|---|---|
| `epr_pairs` | Pairs delivered |
| `epr_attempts` | Attempts made to deliver them, the successful ones included |
| `pair_fidelity` | Mean fidelity of the heralded pairs to their Bell state, before nuclear dephasing |
| `pair_time_ns` | Generation time of each pair, in delivery order |

NetQMPI adds the simulated time of each shot in
`comm.metrics["netqmpi"]["sim_time_ns"]`. With NetQMPI's own links the plugin
reports nothing.

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

## Checked on NetQMPI alone

- **Telegates**: `expose`/`unexpose` were checked on an ideal device, with
  both NetQMPI's links and a perfect heralded link (`tests/`). The remote
  CNOT reproduces its truth table, and `unexpose` restores the phase of a
  control in |+⟩. One root exposing to two receivers flips both targets.
- **Link metrics** on the presets: the measured cycle time (13.23 µs) and
  heralded fidelity (NV 0.5865, SnV 0.7758) equal the double-click model's.
  The attempts per pair agree with 1/p within sampling error: about
  1.58 million for NV and 4,379 for SnV.

## Not yet covered

- **Arbitrary angles.** NetQASM encodes a rotation as n·π/2^d. Multiples of
  π/4 are exact, but any other angle (for example the phases of `Long`,
  DEGGA, or DEGA with 3-bit chunks) is split into several rotations, and each
  one adds gate noise and time.
- **Telegates against the NetSquid code.** `examples/telegate.py` has not
  yet been compared with `telegate.py` of the original emulator under noise.
