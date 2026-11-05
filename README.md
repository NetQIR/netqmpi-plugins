# NetQMPI plugins

Hardware and link models for [NetQMPI](https://github.com/NetQIR/netqmpi),
packaged as [simulation plugins](https://netqir.github.io/netqmpi/backends/netqasm-plugins.html).
A plugin changes how a backend simulates the network without touching
NetQMPI or the program: the same SPMD script runs on ideal nodes or on a
characterised platform by changing its configuration.

| Plugin | Directory | Entry points | Backend |
|---|---|---|---|
| NV / SnV colour centres, heralded double-click links, telegates, link metrics | [`color-centers/`](color-centers) | `nv_2026`, `snv_2026`, `color_centers` | NetQASM (SquidASM 0.13.6, NetQASM 2.0) |

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
  `nv_2026`. NetQMPI resolves them by short name (`--plugin nv_2026`), and
  `netqmpi --list-plugins` lists them.
- **Protocol.** Each entry point declares `backends`, sets the run settings
  its platform needs in `run_defaults`, and refuses bad parameters or
  incompatible settings in `configure`, before anything is traced (see the
  [plugin guide](https://netqir.github.io/netqmpi/backends/netqasm-plugins.html)).
- **Metrics.** What a plugin measures (pairs, attempts, fidelity) is yielded
  by its context manager under NetQMPI's common key names.
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
netqmpi --list-plugins
```

Then select it by name, on the command line or in the `netqasm` block of a
config file:

```bash
netqmpi -n 2 app.py --netqasm --plugin nv_2026
netqmpi -n 2 app.py --netqasm --plugin nv_2026 --plugin-config overrides.yaml --metrics metrics.json
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

Simulation plugins are in NetQMPI `main` but not in a release yet. These
NetQMPI issues are what this repository builds on, all merged:

- [#29](https://github.com/NetQIR/netqmpi/issues/29): short names, the
  `--plugin` flag, run-config defaults, and refusal on unsupported backends.
- [#30](https://github.com/NetQIR/netqmpi/issues/30): a channel for plugins
  to report metrics.
- [#31](https://github.com/NetQIR/netqmpi/issues/31): `expose`/`unexpose`
  (telegates) on NetQASM.
