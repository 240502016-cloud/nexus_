from __future__ import annotations

import io
import os
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.modules.meme_generator.templates import MemeTemplate


CANVAS_SIZE = 1200


def _font(size: int, *, bold: bool = False):
    candidates = [
        os.getenv("MEME_FONT_PATH", ""),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, *, width: int, height: int, max_lines: int):
    for size in range(70, 25, -2):
        font = _font(size, bold=True)
        approx_chars = max(8, int(width / max(1, size * 0.58)))
        lines = textwrap.wrap(text, width=approx_chars, break_long_words=False)
        if len(lines) > max_lines:
            continue
        spacing = max(6, size // 5)
        boxes = [draw.textbbox((0, 0), line, font=font, stroke_width=2) for line in lines]
        total_height = sum(box[3] - box[1] for box in boxes) + spacing * max(0, len(lines) - 1)
        if all(box[2] - box[0] <= width for box in boxes) and total_height <= height:
            return font, lines, total_height, spacing
    raise ValueError("Caption güvenli alana sığmıyor")


def render_card(template: MemeTemplate, captions: dict[str, str], target_path: Path) -> bytes:
    image = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), template.background)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((70, 70, 1130, 1130), radius=52, outline=template.accent, width=8)
    draw.rectangle((70, 70, 1130, 100), fill=template.accent)
    draw.text((100, 125), template.name, font=_font(28, bold=True), fill=template.accent)

    areas = [(115, 270, 1085, 350), (115, 690, 1085, 325)]
    for zone, area in zip(template.zones, areas, strict=True):
        left, top, right, height = area
        width = right - left
        text = captions[zone.key]
        font, lines, total_height, spacing = _fit_text(
            draw, text, width=width, height=height, max_lines=zone.max_lines
        )
        current_y = top + (height - total_height) / 2
        for line in lines:
            box = draw.textbbox((0, 0), line, font=font, stroke_width=2)
            line_width = box[2] - box[0]
            draw.text(
                (left + (width - line_width) / 2, current_y),
                line,
                font=font,
                fill=(248, 250, 252),
                stroke_width=2,
                stroke_fill=(0, 0, 0),
            )
            current_y += box[3] - box[1] + spacing
        if zone.key == "TITLE":
            draw.line((180, 630, 1020, 630), fill=template.accent, width=5)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    rendered = buffer.getvalue()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = target_path.with_suffix(".tmp")
    temporary.write_bytes(rendered)
    temporary.replace(target_path)
    return rendered

