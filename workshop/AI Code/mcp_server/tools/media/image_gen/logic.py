import base64
import io
import os
from mcp.server.fastmcp import FastMCP
from google import genai
from google.genai import types
from PIL import Image

mcp = FastMCP("image-tools")

FORMATTING_TEMPLATES = {
    "Bar Chart — ICICI Brand": (
        "Create a professional bar chart image strictly following ICICI Prudential brand guidelines. "
        "Chart title in dark red. Axis labels and legend in a clean sans-serif font. "
        "Primary bar colors in order: orange, dark red, purple, gold. "
        "Background: clean white. Gridlines: light grey. "
        "Place the ICICI Prudential orange 'i' logo at the bottom-left corner. "
        "Footer disclaimer text at the bottom-right. "
        "Clean, professional, generous white space. "
        "DO NOT show any font names, hex colour codes, or technical style labels anywhere in the image. "
        "DO NOT include a 'Secondary Colors' legend entry — only show the actual data series in the legend. "
    ),
    "Line Chart — ICICI Brand": (
        "Create a professional line chart image strictly following ICICI Prudential brand guidelines. "
        "Chart title in dark red. Axis labels and legend in a clean sans-serif font. "
        "Line colors: orange, dark red, purple, gold for primary series. "
        "Background: white. Grid lines: light grey. Data points clearly marked. "
        "ICICI Prudential orange 'i' logo at the bottom-left. Footer disclaimer at the bottom-right. "
        "Clean professional financial style. "
        "DO NOT show any font names, hex colour codes, or technical style labels anywhere in the image. "
    ),
    "Pie / Donut Chart — ICICI Brand": (
        "Create a professional pie or donut chart image following ICICI Prudential brand guidelines. "
        "Title in dark red. Slice colors: orange, dark red, purple, gold, navy, salmon. "
        "Legend text in a clean sans-serif font. Percentage labels inside slices in white. "
        "White background. ICICI Prudential orange 'i' logo at the bottom-left. "
        "DO NOT show any font names, hex colour codes, or technical style labels anywhere in the image. "
    ),
    "Data Table — ICICI Brand": (
        "Create a professional data table image following ICICI Prudential brand guidelines. "
        "Header row: dark red background with white text. "
        "Body rows: alternating white and very light grey, dark text. "
        "Total/summary row in bold. Cell borders: thin light grey. Generous padding. "
        "Title above the table in dark red. ICICI Prudential orange 'i' logo at the bottom-left. "
        "DO NOT show any font names, hex colour codes, or technical style labels anywhere in the image. "
    ),
    "Icon Grid / Tile Layout — ICICI Brand": (
        "Create a professional icon grid or tile layout image following ICICI Prudential brand guidelines. "
        "Tile colors from the ICICI palette: orange, dark red, navy, gold, salmon, purple, sky blue, warm grey. "
        "Tile text in white on dark tiles, dark text on light tiles. "
        "Rounded corners, consistent padding, clean grid layout. "
        "Title in dark red. ICICI Prudential orange 'i' logo at the bottom-left. "
        "DO NOT show any font names, hex colour codes, or technical style labels anywhere in the image. "
    ),
    "Process Flow / Arrows — ICICI Brand": (
        "Create a professional process flow or chevron/arrow diagram following ICICI Prudential brand guidelines. "
        "Alternating ICICI brand colors for arrow shapes: dark red, navy, warm grey, gold, salmon. "
        "Shape label text in white on dark shapes, dark text on light shapes. "
        "Title in dark red. White background. ICICI Prudential orange 'i' logo at the bottom-left. "
        "DO NOT show any font names, hex colour codes, or technical style labels anywhere in the image. "
    ),
    "Hexagon / SmartArt — ICICI Brand": (
        "Create a professional hexagon cluster or SmartArt-style diagram following ICICI Prudential brand guidelines. "
        "Hexagon colors: mix of orange, dark red, salmon, warm grey, navy. "
        "Central hexagon in navy (largest). Text inside hexagons in white or dark for contrast. "
        "Title in dark red. Clean white background. ICICI Prudential orange 'i' logo at the bottom-left. "
        "DO NOT show any font names, hex colour codes, or technical style labels anywhere in the image. "
    ),
    "Infographic / Text Layout — ICICI Brand": (
        "Create a professional infographic or text-heavy layout following ICICI Prudential brand guidelines. "
        "Title in dark red. Subheadings and body in a clean sans-serif font. "
        "Accent colors for callout boxes: orange and gold. "
        "Background: clean white or very light warm grey. "
        "ICICI Prudential orange 'i' logo at the bottom-left. Professional financial report style. "
        "DO NOT show any font names, hex colour codes, or technical style labels anywhere in the image. "
    ),
    "ICICI Universal Template": (
        "Create an image strictly following ALL ICICI Prudential brand guidelines. "
        "Typography: large bold title, medium bold subtitle, clean body text, small footer note. "
        "Colors: use ONLY ICICI brand colors — orange, dark red, purple, gold (primary); "
        "navy, warm grey, salmon, sky blue (secondary). No other colors. "
        "Layout: white or very light warm-grey background. "
        "ICICI Prudential orange 'i' logo at the bottom-left. Footer text at the bottom. "
        "Clean, professional, presentation-quality output. "
        "DO NOT show any font names, hex colour codes, or technical style labels anywhere in the image. "
    ),
}

MODEL_ID = "gemini-3.1-flash-image-preview"


@mcp.tool()
def generate_image(
    prompt: str,
    template: str | None = None,
    ref_image_bytes: bytes | None = None,
    aspect_ratio: str = "16:9",
    resolution: str = "1K",
) -> dict:
    """
    Generate an image from a text prompt using Gemini's image generation model.

    template: optional ICICI Prudential brand template name.
              Valid values: "Bar Chart — ICICI Brand", "Line Chart — ICICI Brand",
              "Pie / Donut Chart — ICICI Brand", "Data Table — ICICI Brand",
              "Icon Grid / Tile Layout — ICICI Brand", "Process Flow / Arrows — ICICI Brand",
              "Hexagon / SmartArt — ICICI Brand", "Infographic / Text Layout — ICICI Brand",
              "ICICI Universal Template"
    ref_image_bytes: optional reference image bytes (PNG/JPG) for edit-based generation.
    aspect_ratio: "16:9", "1:1", "9:16", "4:3", "3:4"
    resolution: "512", "1K", "2K", "4K"

    Returns: { "image_bytes": bytes, "caption_text": str | None }
    """
    if not prompt:
        raise ValueError("prompt cannot be empty.")

    tpl_text = FORMATTING_TEMPLATES.get(template, "") if template else ""
    final_prompt = f"{tpl_text}\n\nAdditional instructions: {prompt}" if tpl_text else prompt

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    parts = [types.Part.from_text(text=final_prompt)]

    if ref_image_bytes:
        parts.append(types.Part.from_bytes(data=ref_image_bytes, mime_type="image/png"))

    try:
        resp = client.models.generate_content(
            model=MODEL_ID,
            contents=parts,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=types.ImageConfig(aspect_ratio=aspect_ratio, image_size=resolution),
            ),
        )
    except Exception as e:
        raise RuntimeError(f"generate_image: Gemini API call failed. {e}") from e

    out_text, out_bytes = "", None
    for part in resp.parts:
        if getattr(part, "thought", False):
            continue
        if part.text:
            out_text += part.text
        elif part.inline_data:
            out_bytes = part.inline_data.data

    if out_bytes is None:
        raise RuntimeError(
            "generate_image: Gemini returned no image. "
            "Try rephrasing the prompt or switching to a different model."
        )

    return {
        "image_bytes": out_bytes,
        "caption_text": out_text.strip() or None,
    }
