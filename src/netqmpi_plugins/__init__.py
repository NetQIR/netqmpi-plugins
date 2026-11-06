"""
Simulation plugins for NetQMPI.

Each subpackage is one plugin and registers its short names in the
``netqmpi.plugins`` entry-point group, so NetQMPI finds it with
``--plugin NAME`` and lists it with ``netqmpi --list-plugins``. Importing this
package imports no simulator; a plugin imports its own when NetQMPI loads it.

* :mod:`netqmpi_plugins.colorcenters`: NV and SnV colour centres with
  heralded double-click links (``nv_2026``, ``snv_2026``, ``color_centers``),
  for the NetQASM backend. Extra: ``netqmpi-plugins[colorcenters]``.
"""
try:
    from importlib.metadata import PackageNotFoundError, version
except ImportError:  # pragma: no cover - Python < 3.8
    from importlib_metadata import PackageNotFoundError, version

try:
    __version__ = version("netqmpi-plugins")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0+unknown"
