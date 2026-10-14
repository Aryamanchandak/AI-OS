from tool_registry import register
from credit_note_eval_mcp import generate_credit_section, generate_credit_note

register(group="finance")(generate_credit_section)
register(group="finance")(generate_credit_note)
