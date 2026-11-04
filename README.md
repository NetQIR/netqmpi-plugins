# NetQMPI plugins

Hardware and link models for [NetQMPI](https://github.com/NetQIR/netqmpi),
packaged as [simulation plugins](https://netqir.github.io/netqmpi/backends/netqasm-plugins.html).
A plugin changes how a backend simulates the network without touching
NetQMPI or the program: the same SPMD script runs on ideal nodes or on a
characterised platform by changing its configuration.

| Plugin | Directory | Entry points | Backend |
|---|---|---|---|
| NV / SnV colour centres, heralded double-click links | [`color-centers/`](color-centers) | `nv_2026`, `snv_2026`, `color_centers` | NetQASM (SquidASM 0.13.6, NetQASM 2.0) |

## Layout

Each directory is **one plugin and one installable distribution**, with its
own `pyproject.toml`:

```
<platform>/
├── pyproject.toml          # distribution netqmpi-<platform>, entry points
├── README.md               # model, parameters, how it was validated
├── src/netqmpi_<platform>/ # the plugin
├── examples/               # NetQMPI programs + config files
└── tests/
```

Plugins are separate distributions, not one package, because each one pins
its own simulator stack. A SquidASM plugin needs netsquid-magic 16, while
Qoala needs 14, so the two cannot be installed together. You install only
the plugin you use.

### Conventions

- **Names.** The directory is `<platform>`, the distribution is
  `netqmpi-<platform>` and the import package is `netqmpi_<platform>`.
- **Entry points.** Each plugin declares its entry points in the
  `netqmpi.plugins` group, one per characterised platform, for example
  `nv_2026`. Once [NetQIR/netqmpi#29](https://github.com/NetQIR/netqmpi/issues/29)
  lands, NetQMPI resolves them by short name (`--plugin nv_2026`).
- **Presets.** A characterised parameter set ships inside the package, and
  its `plugin_config` only carries overrides. A generic entry point takes
  every parameter, for platforms of your own.
- **Validation.** Each plugin documents what it reproduces and how it was
  checked against the reference model.

## Using a plugin

Install it in the environment that runs NetQMPI's backend. SquidASM and
NetSquid come from the NetSquid index:

```bash
conda activate netqasm2
pip install -e color-centers --no-deps     # deps are already in netqasm2
```

Then name it in the `netqasm` block of the config file:

```yaml
netqasm:
  formalism: dm
  num_qubits: 3
  plugin: netqmpi_colorcenters:nv_2026
```

```bash
netqmpi -n 2 app.py --netqasm --config config.yaml
```

## Adding a plugin

1. Create `<platform>/` with the layout above.
2. Follow the contract and guidelines of the
   [plugin guide](https://netqir.github.io/netqmpi/backends/netqasm-plugins.html):
   validate `plugin_config` and refuse unknown keys, restore everything in
   `finally`, and pin the simulator version.
3. Declare the entry points and add a row to the table above.
4. Add tests that need no statistics: parameters at their limits make the
   expected outcomes certain.

## Status

Simulation plugins are in NetQMPI `main` (9221dfe) but not in a release yet.
Related NetQMPI issues:

- [#29](https://github.com/NetQIR/netqmpi/issues/29): short names, the
  `--plugin` flag, run-config defaults, and refusal on unsupported backends.
- [#30](https://github.com/NetQIR/netqmpi/issues/30): a channel for plugins
  to report metrics.
- [#31](https://github.com/NetQIR/netqmpi/issues/31): `expose`/`unexpose`
  (telegates) on NetQASM.
