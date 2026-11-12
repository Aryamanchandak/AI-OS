from tool_registry import register
from .logic import build_rent_roll, build_clause_report, process_lease_deed

for _fn in (build_rent_roll, build_clause_report, process_lease_deed):
    register(group="finance")(_fn)
