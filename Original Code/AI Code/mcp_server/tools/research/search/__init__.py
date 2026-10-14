# Importing tool triggers the @register(group="research") decorators for all
# five search functions. clients.py is imported transitively by tool.py.
from . import tool  # noqa: F401
