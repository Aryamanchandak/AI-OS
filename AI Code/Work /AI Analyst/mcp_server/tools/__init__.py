"""
Auto-imports every subpackage under groups/.
Adding a new group directory + __init__.py (with its tool imports) is all that's needed.
"""
import importlib
import pkgutil
import os

_GROUPS_DIR = os.path.dirname(__file__)

for _finder, _name, _ispkg in pkgutil.iter_modules([_GROUPS_DIR]):
    if _ispkg:
        importlib.import_module(f"groups.{_name}")
