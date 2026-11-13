# `src/consequence_radar/__init__.py` — explained

This is the top-level package marker for `consequence_radar`. It is four lines: a one-line docstring describing the project ("Consequence Radar: auditable causal research for Indian equities") and a single `__version__ = "0.1.0"` string constant.

It has no logic, no imports, and no side effects. Its only real function is to make `src/consequence_radar/` importable as a package and to expose `consequence_radar.__version__` to anything that wants to read the package version (e.g. `pyproject.toml` tooling, a future `--version` CLI flag, or diagnostics/log lines). Nothing in the codebase currently appears to read `__version__` at runtime based on this file alone — it exists as standard packaging convention rather than active plumbing.

Every other module in `src/consequence_radar/` is a sub-package of this one; this file doesn't re-export anything from them, so importing `consequence_radar` alone gives you only the version string, not any of the pipeline's classes or functions.
