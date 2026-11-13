"""Window screenshots retain the driver's coordinate mapping without rescaling."""
import base64
import io
from PIL import Image, ImageDraw

def image_bytes(snapshot):
    encoded = snapshot.screenshot.get("screenshot_png_b64")
    if not encoded:
        raise PermissionError("Driver returned no window screenshot; grant Screen Recording to CuaDriver")
    return base64.b64decode(encoded, validate=True)

def annotate(png, elements=(), scale=1):
    image = Image.open(io.BytesIO(png)).convert("RGB")
    draw = ImageDraw.Draw(image)
    for row in range(4):
        for col in range(6):
            x, y = col * image.width // 6, row * image.height // 4
            draw.text((x + 3, y + 3), f"R{row + 1}C{col + 1}", fill="#ff63d8", stroke_width=1,
                      stroke_fill="#111111")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()

def to_data_url(png):
    return "data:image/png;base64," + base64.b64encode(png).decode()
