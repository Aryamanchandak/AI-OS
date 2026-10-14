from tool_registry import register
from .logic import generate_credit_section, generate_credit_note

for _fn in (generate_credit_section, generate_credit_note):
    register(group="finance")(_fn)
