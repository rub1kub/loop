from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .service import PALETTE, SIZE


def render_card(pixels: bytes, x: int, y: int) -> bytes:
    """A real, immutable crop of the shared board; no generated game result."""
    board = Image.new("RGB", (SIZE, SIZE))
    board.putdata([tuple(bytes.fromhex(PALETTE[color][1:])) for color in pixels])
    left, top = min(max(x - 24, 0), SIZE - 48), min(max(y - 24, 0), SIZE - 48)
    crop = board.crop((left, top, left + 48, top + 48)).resize((768, 768), Image.Resampling.NEAREST)
    image = Image.new("RGB", (1080, 1080), "#080809")
    image.paste(crop, (156, 150))
    draw = ImageDraw.Draw(image)
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.load_default(size=34)
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ):
        if Path(path).exists():
            font = ImageFont.truetype(path, 34)
            break
    draw.text((156, 65), "LOOP / ПОЛОТНО", font=font, fill="white")
    draw.text((156, 957), "ПОМОГИ ДОРИСОВАТЬ", font=font, fill="white")
    output = BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue()
