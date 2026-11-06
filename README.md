# NetQMPI plugins

Hardware and link models for [NetQMPI](https://github.com/NetQIR/netqmpi),
packaged as [simulation plugins](https://netqir.github.io/netqmpi/backends/netqasm-plugins.html).
A plugin changes how a backend simulates the network without touching
NetQMPI or the program: the same SPMD script runs on ideal nodes or on a
characterised platform by changing its configuration.

| Plugin | Extra | Entry points | Backend |
|---|---|---|---|
| [NV / SnV colour centres](colorcenters), heralded double-click links, telegates, link metrics | `colorcenters` | `nv_2026`, `snv_2026`, `color_centers` | NetQASM (SquidASM 0.13.6, NetQASM 2.0) |

## Installing

Every plugin ships in one distribution, `netqmpi-plugins`, which needs NetQMPI
0.4.0 or later. Each plugin's simulator stack is an **extra**: choose the
plugins you want, or `all`. SquidASM and NetSquid come from the
[NetSquid index](https://forum.netsquid.org/), which needs a (free) account:

```bash
# every plugin
pip install "netqmpi-plugins[all]" --extra-index-url https://pypi.netsquid.org

# only the colour-centre plugin
pip install "netqmpi-plugins[colorcenters]" --extra-index-url https://pypi.netsquid.org

netqmpi --list-plugins
```

Without an extra, `pip install netqmpi-plugins` installs the plugins' code
and NetQMPI but no simulator, and loading a plugin then fails with the extra
it needs. In an environment that already has the simulator stack (for
example `netqasm2`), `pip install netqmpi-plugins --no-deps` is enough.

`all` holds the plugins that can be installed together. A plugin on another
simulator stack (Qoala needs netsquid-magic 14, SquidASM 16) will have its
own extra and stay out of `all`.

## Using a plugin

Select it by name, on the command line or in the `netqasm` block of a config
file:

```bash
netqmpi -n 2 app.py --netqasm --plugin nv_2026
netqmpi -n 2 app.py --netqasm --plugin nv_2026 --plugin-config overrides.yaml --metrics metrics.json
```

Each plugin's README describes its model, parameters, metrics and how it was
validated.

## Layout

```
pyproject.toml                  # the distribution: extras and entry points
src/netqmpi_plugins/<plugin>/   # the code of each plugin
<plugin>/
├── README.md                   # model, parameters, how it was validated
├── examples/                   # NetQMPI programs + config files
└── tests/
```

### Conventions

- **Names.** A plugin is the subpackage `netqmpi_plugins.<plugin>`, its
  directory `<plugin>/` and its extra `[<plugin>]`.
- **Dependencies.** The plugin's simulator stack goes in its extra, never in
  the base dependencies, and the plugin raises an `ImportError` naming the
  extra when the stack is missing. Importing `netqmpi_plugins` imports no
  simulator.
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

## Adding a plugin

1. Add `src/netqmpi_plugins/<plugin>/` and `<plugin>/` with the layout above.
2. Follow the contract and guidelines of the
   [plugin guide](https://netqir.github.io/netqmpi/backends/netqasm-plugins.html):
   validate `plugin_config` and refuse unknown keys, restore everything in
   `finally`, and pin the simulator version.
3. In `pyproject.toml`, declare its entry points, its extra (and add it to
   `all` if its stack is compatible with the others), its package data and
   its tests; add a row to the table above and an entry to the changelog.
4. Add tests that need no statistics: parameters at their limits make the
   expected outcomes certain.

## Developing

```bash
conda activate netqasm2           # SquidASM 0.13.6, NetQASM 2.0, NetQMPI >= 0.4.0
pip install -e . --no-deps
python -m pytest
```

## Releasing

1. Update `version` in `pyproject.toml` and `CHANGELOG.md`.
2. Publish a GitHub release tagged `v<version>`. The
   [publish workflow](.github/workflows/publish.yml) builds the distribution,
   checks that the tag matches the version and uploads it to PyPI with
   trusted publishing.

## License

[Apache 2.0](LICENSE). The colour-centre plugin ports the model of the
COMPUTAEX NetSquid emulator; see [NOTICE](NOTICE).
