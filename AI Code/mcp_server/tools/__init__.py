"""
Single tool root.

Auto-discovers every ``<group>`` subpackage under ``tools/``. Each group package
in turn auto-discovers its own tool subpackages (same mechanism, one level down),
and each tool subpackage self-registers its functions via ``tool_registry.register``.

Convention: subpackages whose name starts with ``_`` (e.g. ``_shared``,
``_pipeline_core``) are NOT auto-imported as tools — they are shared support code,
imported explicitly by the tools that need them.
"""
import importlib
import pkgutil
import os

_DIR = os.path.dirname(__file__)

for _finder, _name, _ispkg in pkgutil.iter_modules([_DIR]):
    if _ispkg and not _name.startswith("_"):
        importlib.import_module(f"{__name__}.{_name}")
