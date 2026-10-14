from tool_registry import register
from .logic import generate_image

register(group="media")(generate_image)
