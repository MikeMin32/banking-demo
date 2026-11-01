"""Compose 1280×360 banner PNGs with a single optically centered title.

Backgrounds live in assets/banner-sources/bg-*.jpg (no baked-in text).
Output is written to assets/banners/*.png.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "banner-sources"
DST = ROOT / "assets" / "banners"
WIDTH, HEIGHT = 1280, 360
CX, CY = WIDTH // 2, HEIGHT // 2
FONT_PATH = "/usr/share/fonts/truetype/lato/Lato-Bold.ttf"

TITLES: dict[str, str] = {
    "dashboard": "Dashboard",
    "accounts": "Accounts",
    "account-details": "Account Details",
    "balance-summary": "Balance Summary",
    "add-account": "Add Account",
    "expected-charges": "Expected Charges",
    "login-details": "Login Details",
    "settings": "Settings",
}


def _fit_font(title: str, max_width: int = 980) -> ImageFont.FreeTypeFont:
    size = 78 if len(title) <= 12 else 68 if len(title) <= 16 else 60
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    while size >= 42:
        font = ImageFont.truetype(FONT_PATH, size)
        bbox = probe.textbbox((0, 0), title, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
        size -= 2
    return ImageFont.truetype(FONT_PATH, 42)


def _ink_bbox(title: str, font: ImageFont.FreeTypeFont) -> tuple[int, int, int, int]:
    """Actual glyph ink bounds relative to the text draw origin."""
    probe = Image.new("L", (1200, 300), 0)
    draw = ImageDraw.Draw(probe)
    origin = (50, 150)
    draw.text(origin, title, font=font, fill=255)
    ink = ImageChops.difference(probe, Image.new("L", probe.size, 0)).getbbox()
    if ink is None:
        raise RuntimeError(f"no ink for title: {title!r}")
    left, top, right, bottom = ink
    return left - origin[0], top - origin[1], right - origin[0], bottom - origin[1]


def _prepare_background(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGB")
    scale = WIDTH / img.width
    resized = img.resize((WIDTH, int(img.height * scale + 0.5)), Image.Resampling.LANCZOS)
    top = max((resized.height - HEIGHT) // 2, 0)
    return resized.crop((0, top, WIDTH, top + HEIGHT))


def compose(bg_path: Path, title: str) -> Image.Image:
    base = _prepare_background(bg_path).convert("RGBA")
    font = _fit_font(title)
    left, top, right, bottom = _ink_bbox(title, font)
    origin_x = CX - (left + right) / 2
    origin_y = CY - (top + bottom) / 2

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    ImageDraw.Draw(overlay).ellipse(
        (CX - 430, CY - 95, CX + 430, CY + 95),
        fill=(6, 18, 42, 72),
    )
    composed = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(composed)
    for dx, dy in ((2, 2), (1, 1)):
        draw.text((origin_x + dx, origin_y + dy), title, font=font, fill=(0, 0, 0, 120))
    draw.text((origin_x, origin_y), title, font=font, fill=(255, 255, 255, 255))
    return ImageEnhance.Contrast(composed.convert("RGB")).enhance(1.02)


def write_contact_sheet(paths: list[Path], out: Path) -> None:
    sheets = [Image.open(path) for path in paths]
    sheet = Image.new("RGB", (WIDTH * 2, HEIGHT * 4), (8, 16, 32))
    for index, image in enumerate(sheets):
        row, col = divmod(index, 2)
        sheet.paste(image, (col * WIDTH, row * HEIGHT))
    sheet.resize((WIDTH, HEIGHT * 2), Image.Resampling.LANCZOS).save(out, format="PNG", optimize=True)


def main() -> None:
    DST.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for slug, title in TITLES.items():
        src = SRC / f"bg-{slug}.jpg"
        if not src.exists():
            raise FileNotFoundError(f"missing banner source: {src}")
        out = DST / f"{slug}.png"
        compose(src, title).save(out, format="PNG", optimize=True)
        outputs.append(out)
        print(out)
    write_contact_sheet(outputs, DST / "_contact-sheet.png")
    print(DST / "_contact-sheet.png")


if __name__ == "__main__":
    main()
