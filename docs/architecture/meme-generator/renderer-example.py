"""Deterministic Pillow rendering example for the Meme Generator design.

This is intentionally independent from FastAPI/SQLAlchemy. The production service resolves trusted
asset IDs to paths before calling the renderer; client-supplied paths must never reach this module.
Requires Pillow and packaged Noto Sans font files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

CANVAS_SIZE = (1200, 1200)
Image.MAX_IMAGE_PIXELS = 40_000_000


@dataclass(frozen=True)
class CaptionZone:
    x: int
    y: int
    width: int
    height: int
    max_lines: int
    min_font_size: int
    max_font_size: int
    align: str = "center"
    fill: str = "white"
    stroke_fill: str = "black"
    stroke_width: int = 3


def _split_long_token(draw: ImageDraw.ImageDraw, token: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    parts: list[str] = []
    current = ""
    for char in token:
        candidate = current + char
        if current and draw.textlength(candidate, font=font) > width:
            parts.append(current)
            current = char
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words: list[str] = []
    for token in text.strip().split():
        if draw.textlength(token, font=font) <= width:
            words.append(token)
        else:
            words.extend(_split_long_token(draw, token, font, width))

    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if current and draw.textlength(candidate, font=font) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _fit_caption(
    draw: ImageDraw.ImageDraw,
    text: str,
    zone: CaptionZone,
    font_path: Path,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    for font_size in range(zone.max_font_size, zone.min_font_size - 1, -2):
        font = ImageFont.truetype(str(font_path), font_size)
        lines = _wrap_text(draw, text, font, zone.width)
        if not lines or len(lines) > zone.max_lines:
            continue
        line_gap = max(4, font_size // 8)
        box = draw.multiline_textbbox(
            (0, 0),
            "\n".join(lines),
            font=font,
            spacing=line_gap,
            align=zone.align,
            stroke_width=zone.stroke_width,
        )
        if box[2] - box[0] <= zone.width and box[3] - box[1] <= zone.height:
            return font, lines
    raise ValueError("Caption does not fit its template zone")


def _draw_caption(
    image: Image.Image,
    text: str,
    zone: CaptionZone,
    font_path: Path,
) -> None:
    draw = ImageDraw.Draw(image)
    font, lines = _fit_caption(draw, text, zone, font_path)
    rendered = "\n".join(lines)
    spacing = max(4, font.size // 8)
    box = draw.multiline_textbbox(
        (0, 0),
        rendered,
        font=font,
        spacing=spacing,
        align=zone.align,
        stroke_width=zone.stroke_width,
    )
    text_width = box[2] - box[0]
    text_height = box[3] - box[1]
    x = zone.x + (zone.width - text_width) / 2
    y = zone.y + (zone.height - text_height) / 2 - box[1]
    draw.multiline_text(
        (x, y),
        rendered,
        font=font,
        fill=zone.fill,
        spacing=spacing,
        align=zone.align,
        stroke_width=zone.stroke_width,
        stroke_fill=zone.stroke_fill,
    )


def render_two_caption_meme(
    trusted_input_path: Path,
    trusted_output_path: Path,
    font_path: Path,
    top_text: str,
    bottom_text: str,
) -> None:
    if len(top_text) > 48 or len(bottom_text) > 48:
        raise ValueError("Caption exceeds the template character limit")

    with Image.open(trusted_input_path) as source:
        source.load()
        normalized = ImageOps.exif_transpose(source).convert("RGB")
        canvas = ImageOps.fit(normalized, CANVAS_SIZE, method=Image.Resampling.LANCZOS)

    top = CaptionZone(48, 36, 1104, 220, max_lines=2, min_font_size=30, max_font_size=62)
    bottom = CaptionZone(48, 944, 1104, 220, max_lines=2, min_font_size=30, max_font_size=62)
    _draw_caption(canvas, top_text, top, font_path)
    _draw_caption(canvas, bottom_text, bottom, font_path)

    trusted_output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(trusted_output_path, format="PNG", optimize=True)
