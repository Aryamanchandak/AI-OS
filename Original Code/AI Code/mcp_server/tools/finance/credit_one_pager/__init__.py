from tool_registry import register
from .logic import generate_credit_one_pager

register(group="finance")(generate_credit_one_pager)
