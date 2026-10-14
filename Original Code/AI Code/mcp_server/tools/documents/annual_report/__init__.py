from tool_registry import register
from .logic import analyze_annual_report

register(group="documents")(analyze_annual_report)
