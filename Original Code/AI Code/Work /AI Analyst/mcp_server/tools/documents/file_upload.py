from tool_registry import register
from file_upload_mcp import upload_file

register(group="documents")(upload_file)
