# Importing tool triggers the register(group="media")(...) calls at the bottom of
# tool.py for all 11 podcast-pipeline tools (list/download/summarize/push/status/etc.).
from . import tool  # noqa: F401
