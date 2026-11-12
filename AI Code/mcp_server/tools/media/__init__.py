"""
Group package.

Auto-discovers each tool subpackage in this group and imports it, which triggers
that tool's ``tool_registry.register`` call. Subpackages whose name starts with
``_`` (shared support code) are skipped.
"""
import importlib
import pkgutil
import os

_DIR = os.path.dirname(__file__)

for _finder, _name, _ispkg in pkgutil.iter_modules([_DIR]):
    if _ispkg and not _name.startswith("_"):
        importlib.import_module(f"{__name__}.{_name}")
