from tool_registry import register
from .logic import upload_file_to_gemini

register(group="utility")(upload_file_to_gemini)
