# Changelog

All notable changes to netqmpi-plugins. Versions follow
[semantic versioning](https://semver.org/); before 1.0, a minor version may
change a plugin's parameters or entry points.

## 0.1.0 — 2026-11-06

First release. Needs NetQMPI 0.4.0 or later, the first release with
simulation plugins.

- One distribution, `netqmpi-plugins`, with every plugin inside; each plugin's
  simulator stack is an extra (`[colorcenters]`, `[all]`).
- **colorcenters** (NetQASM backend, SquidASM 0.13.6): NV and SnV
  colour-centre QPUs with heralded double-click links, ported from the
  COMPUTAEX NetSquid emulator.
  - Entry points `nv_2026` and `snv_2026` (COMPUTAEX 2026 parameter sets,
    overridable through `plugin_config`) and `color_centers` (every parameter
    given).
  - Native decompositions of NetQMPI's gates into the platform's physical
    instructions; pairs land on the electron spin.
  - Link metrics in `comm.metrics["plugin"]`: pairs, attempts, heralded
    fidelity and generation time of each pair.
  - Examples: distributed exact Grover (DEGA, 2-bit chunks), teleportation and
    telegates.
