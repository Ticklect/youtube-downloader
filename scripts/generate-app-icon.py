"""Generate the Beta's Windows application icon from its simple vector shapes.

Requires Pillow only when regenerating artwork. The generated PNG and ICO are
checked in as build inputs, so ordinary Cargo builds do not require Python.
"""

from pathlib import Path
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

# Supersampling preserves the play glyph's sharp silhouette at taskbar sizes.
SIZE = 1024
image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)

# Deep red shadow defines the tile on both dark and light Windows taskbars.
draw.rounded_rectangle((58, 78, 966, 974), radius=222, fill=(70, 8, 23, 85))
draw.rounded_rectangle((58, 50, 966, 946), radius=220, fill="#E60032")

# The play symbol is deliberately oversized, without lettering or tiny detail:
# it stays recognizable even in a 16px title bar.
draw.polygon([(401, 290), (401, 714), (754, 502)], fill="#FFFFFF")

image.save(ASSETS / "app-icon.png", optimize=True)
image.save(
    ASSETS / "app-icon.ico",
    format="ICO",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)

print("Generated assets/app-icon.png and assets/app-icon.ico")
