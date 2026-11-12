from tool_registry import register
from ara_mcp import analyze_annual_report

register(group="documents")(analyze_annual_report)
