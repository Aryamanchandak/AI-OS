"""Auto-import every tool module in this package.

Importing a module runs its `@mcp.tool()` decorators, which registers the tools.
So adding a new tool file requires zero changes here — it's picked up on import.
"""

import importlib
import pkgutil
from pathlib import Path

for _mod in pkgutil.iter_modules([str(Path(__file__).parent)]):
    importlib.import_module(f"{__name__}.{_mod.name}")
