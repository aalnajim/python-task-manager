#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
ICON_DIR = ASSETS_DIR / "icon"
ICONSET_DIR = ICON_DIR / "python-task-manager.iconset"
BASE_PNG = ICON_DIR / "app-icon-1024.png"
ICNS_PATH = ICON_DIR / "python-task-manager.icns"


def rounded_mask(size: int, inset: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((inset, inset, size - inset, size - inset), radius=radius, fill=255)
    return mask


def diagonal_gradient(size: int, start: tuple[int, int, int], end: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGBA", (size, size))
    pixels = image.load()
    scale = max(1, size - 1)
    for y in range(size):
        for x in range(size):
            mix = (x + y) / (2 * scale)
            r = int(start[0] + (end[0] - start[0]) * mix)
            g = int(start[1] + (end[1] - start[1]) * mix)
            b = int(start[2] + (end[2] - start[2]) * mix)
            pixels[x, y] = (r, g, b, 255)
    return image


def radial_glow(size: int, color: tuple[int, int, int], opacity: int, offset: tuple[float, float], radius: float) -> Image.Image:
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    cx = int(size * offset[0])
    cy = int(size * offset[1])
    r = int(size * radius)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=opacity)
    mask = mask.filter(ImageFilter.GaussianBlur(size * 0.09))
    glow.paste((*color, 255), mask=mask)
    return glow


def add_shadow(image: Image.Image, bounds: tuple[int, int, int, int], radius: int, opacity: int, blur: int) -> None:
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(bounds, radius=radius, fill=(0, 0, 0, opacity))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    image.alpha_composite(shadow)


def draw_check(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], fill: tuple[int, int, int, int], width: int) -> None:
    draw.line(points[:2], fill=fill, width=width, joint="curve")
    draw.line(points[1:], fill=fill, width=width, joint="curve")


def build_master_icon(size: int = 1024) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    base = diagonal_gradient(size, (7, 27, 56), (33, 129, 191))
    base.alpha_composite(radial_glow(size, (255, 142, 61), 170, (0.82, 0.18), 0.26))
    base.alpha_composite(radial_glow(size, (94, 234, 212), 120, (0.18, 0.82), 0.32))

    mask = rounded_mask(size, int(size * 0.07), int(size * 0.22))
    shell = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shell.paste(base, mask=mask)
    canvas.alpha_composite(shell)

    overlay = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    overlay_mask = Image.new("L", (size, size), 0)
    overlay_draw = ImageDraw.Draw(overlay_mask)
    overlay_draw.pieslice(
        (int(size * 0.1), int(size * 0.02), int(size * 0.96), int(size * 0.72)),
        start=198,
        end=332,
        fill=120,
    )
    overlay_mask = overlay_mask.filter(ImageFilter.GaussianBlur(size * 0.03))
    overlay.paste((255, 255, 255, 90), mask=overlay_mask)
    canvas.alpha_composite(overlay)

    ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ring_draw = ImageDraw.Draw(ring)
    ring_draw.arc(
        (int(size * 0.17), int(size * 0.16), int(size * 0.84), int(size * 0.83)),
        start=214,
        end=18,
        fill=(255, 255, 255, 120),
        width=int(size * 0.032),
    )
    ring = ring.filter(ImageFilter.GaussianBlur(size * 0.006))
    canvas.alpha_composite(ring)

    panel_bounds = (
        int(size * 0.19),
        int(size * 0.18),
        int(size * 0.76),
        int(size * 0.82),
    )
    add_shadow(canvas, panel_bounds, int(size * 0.09), 90, int(size * 0.032))

    panel = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    panel_draw = ImageDraw.Draw(panel)
    panel_draw.rounded_rectangle(panel_bounds, radius=int(size * 0.09), fill=(246, 251, 255, 255))
    panel_draw.rounded_rectangle(
        (panel_bounds[0] + int(size * 0.03), panel_bounds[1] + int(size * 0.03), panel_bounds[2] - int(size * 0.03), panel_bounds[1] + int(size * 0.16)),
        radius=int(size * 0.06),
        fill=(227, 239, 250, 255),
    )
    canvas.alpha_composite(panel)

    draw = ImageDraw.Draw(canvas)

    card_x = panel_bounds[0] + int(size * 0.08)
    line_left = panel_bounds[0] + int(size * 0.22)
    row_specs = [
        (int(size * 0.36), (48, 209, 88, 255), "check"),
        (int(size * 0.50), (255, 153, 51, 255), "check"),
        (int(size * 0.64), (99, 102, 241, 255), "spark"),
    ]
    text_colors = [(102, 126, 154, 255), (153, 173, 194, 255)]
    stroke = int(size * 0.024)
    for index, (cy, accent, kind) in enumerate(row_specs):
        badge_bounds = (
            card_x,
            cy - int(size * 0.045),
            card_x + int(size * 0.11),
            cy + int(size * 0.045),
        )
        draw.rounded_rectangle(badge_bounds, radius=int(size * 0.028), fill=ImageChops.add(Image.new("RGBA", (1, 1), accent), Image.new("RGBA", (1, 1), (10, 10, 10, 0))).getpixel((0, 0)))
        if kind == "check":
            draw_check(
                draw,
                [
                    (card_x + int(size * 0.024), cy + int(size * 0.004)),
                    (card_x + int(size * 0.045), cy + int(size * 0.028)),
                    (card_x + int(size * 0.085), cy - int(size * 0.018)),
                ],
                (255, 255, 255, 255),
                stroke,
            )
        else:
            draw.line(
                [
                    (card_x + int(size * 0.056), cy - int(size * 0.03)),
                    (card_x + int(size * 0.04), cy + int(size * 0.012)),
                    (card_x + int(size * 0.066), cy + int(size * 0.012)),
                    (card_x + int(size * 0.05), cy + int(size * 0.042)),
                ],
                fill=(255, 255, 255, 255),
                width=int(size * 0.018),
            )

        top_y = cy - int(size * 0.02)
        bottom_y = cy + int(size * 0.03)
        draw.rounded_rectangle(
            (line_left, top_y, panel_bounds[2] - int(size * 0.08), top_y + int(size * 0.022)),
            radius=int(size * 0.012),
            fill=text_colors[0],
        )
        draw.rounded_rectangle(
            (line_left, bottom_y, panel_bounds[2] - int(size * (0.16 + index * 0.05)), bottom_y + int(size * 0.018)),
            radius=int(size * 0.01),
            fill=text_colors[1],
        )

    tab_bounds = (
        panel_bounds[0] + int(size * 0.17),
        panel_bounds[1] - int(size * 0.045),
        panel_bounds[0] + int(size * 0.4),
        panel_bounds[1] + int(size * 0.05),
    )
    draw.rounded_rectangle(tab_bounds, radius=int(size * 0.04), fill=(210, 225, 240, 255))

    badge_center = (int(size * 0.73), int(size * 0.73))
    badge_radius = int(size * 0.115)
    add_shadow(
        canvas,
        (
            badge_center[0] - badge_radius,
            badge_center[1] - badge_radius,
            badge_center[0] + badge_radius,
            badge_center[1] + badge_radius,
        ),
        badge_radius,
        110,
        int(size * 0.025),
    )
    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    badge_draw = ImageDraw.Draw(badge)
    badge_draw.ellipse(
        (
            badge_center[0] - badge_radius,
            badge_center[1] - badge_radius,
            badge_center[0] + badge_radius,
            badge_center[1] + badge_radius,
        ),
        fill=(255, 109, 61, 255),
    )
    badge_draw.ellipse(
        (
            badge_center[0] - int(size * 0.07),
            badge_center[1] - int(size * 0.07),
            badge_center[0] + int(size * 0.07),
            badge_center[1] + int(size * 0.07),
        ),
        fill=(255, 167, 84, 90),
    )
    canvas.alpha_composite(badge)

    number_draw = ImageDraw.Draw(canvas)
    number_draw.text(
        (badge_center[0], badge_center[1] - int(size * 0.015)),
        "3",
        anchor="mm",
        fill=(255, 255, 255, 255),
        font_size=int(size * 0.12),
        stroke_width=int(size * 0.01),
        stroke_fill=(210, 80, 40, 180),
    )

    return canvas


def save_icon_variants() -> None:
    ASSETS_DIR.mkdir(exist_ok=True)
    ICON_DIR.mkdir(exist_ok=True)
    ICONSET_DIR.mkdir(exist_ok=True)

    master = build_master_icon(1024)
    master.save(BASE_PNG)

    sizes = [16, 32, 64, 128, 256, 512, 1024]
    variants: dict[int, Image.Image] = {}
    for size in sizes:
        variants[size] = master.resize((size, size), Image.Resampling.LANCZOS)

    iconset_specs = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]
    for filename, size in iconset_specs:
        variants[size].save(ICONSET_DIR / filename)

    master.save(ICNS_PATH, format="ICNS", append_images=[variants[32], variants[64], variants[128], variants[256], variants[512]])


def main() -> int:
    save_icon_variants()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
