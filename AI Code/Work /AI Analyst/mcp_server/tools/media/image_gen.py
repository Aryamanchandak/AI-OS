from tool_registry import register
from image_gen_mcp import generate_image

register(group="media")(generate_image)
