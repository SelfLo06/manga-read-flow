#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT_DIR / "data" / "local" / "datasets" / "110-detection" / "synthetic-samples-v0.1"
WIDTH = 1000
HEIGHT = 1500
GENERATED_AT = "2026-07-09T00:00:00Z"
GENERATED_FILE_NAMES = (
    "synthetic_01_clean_dialogue.webp",
    "synthetic_02_narration_boxes.webp",
    "synthetic_03_small_bubble_overflow.webp",
    "synthetic_04_complex_background_skip.webp",
    "manifest.json",
)

FONT_CANDIDATES = [
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansJP-Regular.otf"),
    Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
    Path("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"),
    Path("C:/Windows/Fonts/msgothic.ttc"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]


@dataclass(frozen=True)
class FontSet:
    regular_path: Path | None

    def regular(self, size: int) -> ImageFont.ImageFont:
        if self.regular_path is None:
            return ImageFont.load_default(size=size)
        return ImageFont.truetype(str(self.regular_path), size=size)


def find_font_set() -> FontSet:
    for font_path in FONT_CANDIDATES:
        if font_path.exists():
            return FontSet(font_path)
    return FontSet(None)


def text_bbox(font: ImageFont.ImageFont, text: str) -> tuple[int, int]:
    left, top, right, bottom = font.getbbox(text)
    return right - left, bottom - top


def wrap_japanese_text(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    line = ""
    for char in text:
        candidate = line + char
        if line and text_bbox(font, candidate)[0] > max_width:
            lines.append(line)
            line = char
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int] = (20, 20, 20),
    line_gap: int = 8,
) -> None:
    x, y, width, height = box
    lines = wrap_japanese_text(text, font, max(width - 44, 1))
    line_sizes = [text_bbox(font, line) for line in lines]
    total_height = sum(size[1] for size in line_sizes) + line_gap * max(len(lines) - 1, 0)
    current_y = y + max((height - total_height) // 2, 0)
    for line, (line_width, line_height) in zip(lines, line_sizes):
        draw.text((x + (width - line_width) / 2, current_y), line, font=font, fill=fill)
        current_y += line_height + line_gap


def draw_vertical_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int] = (20, 20, 20),
    char_gap: int = 4,
) -> None:
    x, y, width, height = box
    char_sizes = [text_bbox(font, char) for char in text]
    total_height = sum(size[1] for size in char_sizes) + char_gap * max(len(text) - 1, 0)
    current_y = y + max((height - total_height) // 2, 0)
    for char, (char_width, char_height) in zip(text, char_sizes):
        draw.text((x + (width - char_width) / 2, current_y), char, font=font, fill=fill)
        current_y += char_height + char_gap


def draw_bubble(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    tail_to: tuple[int, int] | None = None,
    fill: tuple[int, int, int] = (255, 255, 255),
    outline: tuple[int, int, int] = (20, 20, 20),
) -> None:
    x, y, width, height = box
    draw.ellipse((x, y, x + width, y + height), fill=fill, outline=outline, width=5)
    if tail_to is not None:
        draw.polygon(
            [
                (x + width // 2 - 28, y + height - 8),
                (x + width // 2 + 18, y + height - 10),
                tail_to,
            ],
            fill=fill,
            outline=outline,
        )
        draw.line(
            [
                (x + width // 2 - 28, y + height - 8),
                tail_to,
                (x + width // 2 + 18, y + height - 10),
            ],
            fill=outline,
            width=4,
        )


def draw_narration_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int] = (255, 255, 255),
) -> None:
    x, y, width, height = box
    draw.rectangle((x, y, x + width, y + height), fill=fill, outline=(15, 15, 15), width=5)
    draw.rectangle((x + 12, y + 12, x + width - 12, y + height - 12), outline=(15, 15, 15), width=2)


def draw_panel_grid(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle((42, 42, WIDTH - 42, HEIGHT - 42), outline=(25, 25, 25), width=8)
    draw.line((42, 520, WIDTH - 42, 520), fill=(25, 25, 25), width=5)
    draw.line((42, 1005, WIDTH - 42, 1005), fill=(25, 25, 25), width=5)
    draw.line((500, 42, 500, 520), fill=(25, 25, 25), width=4)
    draw.line((360, 1005, 360, HEIGHT - 42), fill=(25, 25, 25), width=4)


def draw_simple_faces(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse((165, 290, 300, 430), outline=(30, 30, 30), width=5)
    draw.arc((196, 345, 230, 380), 200, 340, fill=(30, 30, 30), width=4)
    draw.arc((237, 345, 272, 380), 200, 340, fill=(30, 30, 30), width=4)
    draw.arc((204, 382, 265, 414), 20, 160, fill=(30, 30, 30), width=4)

    draw.ellipse((675, 670, 820, 820), outline=(30, 30, 30), width=5)
    draw.line((700, 730, 740, 735), fill=(30, 30, 30), width=4)
    draw.line((760, 735, 802, 728), fill=(30, 30, 30), width=4)
    draw.arc((715, 765, 785, 805), 20, 160, fill=(30, 30, 30), width=4)


def region(
    region_id: str,
    region_type: str,
    box: tuple[int, int, int, int],
    text_orientation: str,
    expected_text: str,
    expected_difficulty: str,
    intended_use: str,
) -> dict[str, object]:
    x, y, width, height = box
    return {
        "region_id": region_id,
        "region_type": region_type,
        "bbox": {"x": x, "y": y, "width": width, "height": height},
        "bbox_semantics": "text_container_region",
        "text_orientation": text_orientation,
        "expected_text": expected_text,
        "expected_text_lines": [expected_text],
        "normalized_text": expected_text,
        "language": "ja",
        "expected_difficulty": expected_difficulty,
        "intended_use": intended_use,
    }


def asset_manifest(
    file_name: str,
    image: Image.Image,
    scenario_tags: list[str],
    regions: list[dict[str, object]],
    output_dir: Path,
) -> dict[str, object]:
    return {
        "file_name": file_name,
        "relative_path": f"{output_dir.name}/{file_name}",
        "source_type": "synthetic",
        "width": image.width,
        "height": image.height,
        "color_mode": image.mode,
        "scenario_tags": scenario_tags,
        "regions": regions,
    }


def generate_clean_dialogue(output_dir: Path, fonts: FontSet) -> dict[str, object]:
    image = Image.new("RGB", (WIDTH, HEIGHT), (247, 247, 244))
    draw = ImageDraw.Draw(image)
    draw_panel_grid(draw)
    for offset in range(-HEIGHT, WIDTH, 34):
        draw.line((offset, 1005, offset + 460, HEIGHT - 42), fill=(222, 222, 218), width=2)
    draw_simple_faces(draw)

    bubble_font = fonts.regular(43)
    regions = [
        region("s01_r01", "dialogue_bubble", (95, 105, 360, 185), "horizontal", "こんにちは", "easy", "detection"),
        region("s01_r02", "dialogue_bubble", (560, 245, 330, 180), "horizontal", "そうですね", "easy", "ocr"),
        region("s01_r03", "dialogue_bubble", (220, 745, 420, 205), "horizontal", "これはテストです", "easy", "detection"),
    ]
    for item, tail in zip(regions, [(240, 315), (745, 475), (680, 900)]):
        bbox = item["bbox"]
        box = (bbox["x"], bbox["y"], bbox["width"], bbox["height"])
        draw_bubble(draw, box, tail_to=tail)
        draw_centered_text(draw, box, item["expected_text"], bubble_font)

    file_name = "synthetic_01_clean_dialogue.webp"
    image.save(output_dir / file_name, "WEBP", lossless=True, quality=100, method=6)
    return asset_manifest(file_name, image, ["clean_dialogue", "black_white", "dialogue_bubble"], regions, output_dir)


def generate_narration_boxes(output_dir: Path, fonts: FontSet) -> dict[str, object]:
    image = Image.new("RGB", (WIDTH, HEIGHT), (250, 250, 248))
    draw = ImageDraw.Draw(image)
    draw_panel_grid(draw)
    for y in range(600, 980, 24):
        draw.line((70, y, WIDTH - 70, y + 60), fill=(226, 226, 224), width=2)
    draw.rectangle((110, 635, 330, 975), outline=(35, 35, 35), width=5)
    draw.rectangle((650, 730, 865, 985), outline=(35, 35, 35), width=5)

    horizontal_font = fonts.regular(34)
    vertical_font = fonts.regular(35)
    regions = [
        region("s02_r01", "narration_box", (88, 92, 420, 165), "horizontal", "まだ終わっていない", "easy", "detection"),
        region("s02_r02", "narration_box", (610, 210, 275, 440), "vertical", "どうしてそんなことを", "medium", "ocr"),
        region("s02_r03", "narration_box", (145, 1110, 710, 170), "horizontal", "本当に大丈夫なのか", "easy", "detection"),
    ]

    first = regions[0]["bbox"]
    first_box = (first["x"], first["y"], first["width"], first["height"])
    draw_narration_box(draw, first_box)
    draw_centered_text(draw, first_box, regions[0]["expected_text"], horizontal_font)

    second = regions[1]["bbox"]
    second_box = (second["x"], second["y"], second["width"], second["height"])
    draw_narration_box(draw, second_box)
    draw_vertical_text(draw, second_box, regions[1]["expected_text"], vertical_font)

    third = regions[2]["bbox"]
    third_box = (third["x"], third["y"], third["width"], third["height"])
    draw_narration_box(draw, third_box)
    draw_centered_text(draw, third_box, regions[2]["expected_text"], horizontal_font)

    file_name = "synthetic_02_narration_boxes.webp"
    image.save(output_dir / file_name, "WEBP", lossless=True, quality=100, method=6)
    return asset_manifest(file_name, image, ["narration_box", "black_white", "mixed_layout"], regions, output_dir)


def generate_small_bubble_overflow(output_dir: Path, fonts: FontSet) -> dict[str, object]:
    image = Image.new("RGB", (WIDTH, HEIGHT), (236, 238, 238))
    draw = ImageDraw.Draw(image)
    draw.rectangle((42, 42, WIDTH - 42, HEIGHT - 42), outline=(40, 40, 40), width=8)
    for x in range(70, WIDTH - 70, 46):
        draw.line((x, 80, x + 180, HEIGHT - 80), fill=(218, 221, 221), width=3)
    draw.rectangle((85, 850, 900, 1320), outline=(45, 45, 45), width=5)
    draw.arc((110, 875, 390, 1220), 205, 330, fill=(45, 45, 45), width=5)
    draw.arc((590, 875, 870, 1220), 210, 335, fill=(45, 45, 45), width=5)

    small_font = fonts.regular(24)
    normal_font = fonts.regular(40)
    regions = [
        region(
            "s03_r01",
            "dialogue_bubble",
            (615, 145, 245, 126),
            "horizontal",
            "どうしてそんなことをまだ終わっていない",
            "hard",
            "overflow_risk",
        ),
        region("s03_r02", "dialogue_bubble", (120, 375, 360, 180), "horizontal", "本当に大丈夫なのか", "medium", "ocr"),
    ]

    first = regions[0]["bbox"]
    first_box = (first["x"], first["y"], first["width"], first["height"])
    draw_bubble(draw, first_box, tail_to=(745, 315), fill=(252, 252, 252))
    draw_centered_text(draw, first_box, regions[0]["expected_text"], small_font, line_gap=2)

    second = regions[1]["bbox"]
    second_box = (second["x"], second["y"], second["width"], second["height"])
    draw_bubble(draw, second_box, tail_to=(320, 610), fill=(252, 252, 252))
    draw_centered_text(draw, second_box, regions[1]["expected_text"], normal_font)

    file_name = "synthetic_03_small_bubble_overflow.webp"
    image.save(output_dir / file_name, "WEBP", lossless=True, quality=100, method=6)
    return asset_manifest(file_name, image, ["small_bubble", "overflow_risk", "light_gray"], regions, output_dir)


def textured_background() -> Image.Image:
    small = Image.new("RGB", (250, 375))
    pixels = small.load()
    for y in range(small.height):
        for x in range(small.width):
            base = 116 + ((x * 7 + y * 5) % 66)
            stripe = 22 if (x + y * 2) % 37 < 10 else -10
            pixels[x, y] = (
                max(0, min(255, base + stripe + (y % 19))),
                max(0, min(255, base + 20 - stripe // 2)),
                max(0, min(255, base + 42 + (x % 23) - stripe)),
            )
    return small.resize((WIDTH, HEIGHT), Image.Resampling.BICUBIC)


def paste_angled_text(
    image: Image.Image,
    box: tuple[int, int, int, int],
    text: str,
    font: ImageFont.ImageFont,
) -> None:
    x, y, width, height = box
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    layer_draw = ImageDraw.Draw(layer)
    layer_draw.rounded_rectangle((10, 20, width - 10, height - 20), radius=8, fill=(235, 232, 196, 205))
    draw_centered_text(layer_draw, (10, 20, width - 20, height - 40), text, font, fill=(36, 34, 46))
    rotated = layer.rotate(-9, expand=True, resample=Image.Resampling.BICUBIC)
    image.alpha_composite(rotated, (x - 20, y - 18))


def generate_complex_background_skip(output_dir: Path, fonts: FontSet) -> dict[str, object]:
    image = textured_background().convert("RGBA")
    draw = ImageDraw.Draw(image)
    for y in range(80, HEIGHT, 120):
        draw.line((0, y, WIDTH, y - 180), fill=(70, 78, 92, 65), width=22)
    for x in range(40, WIDTH, 155):
        draw.ellipse((x, 1020, x + 160, 1260), outline=(236, 236, 230, 70), width=8)

    weak_font = fonts.regular(34)
    angled_font = fonts.regular(33)
    hard_font = fonts.regular(28)
    regions = [
        region("s04_r01", "difficult_text", (82, 150, 405, 165), "horizontal", "これはテストです", "hard", "skip_risk"),
        region("s04_r02", "difficult_text", (585, 460, 315, 165), "angled", "まだ終わっていない", "medium", "detection"),
        region("s04_r03", "difficult_text", (185, 1035, 520, 150), "horizontal", "どうしてそんなことを", "hard", "ocr"),
    ]

    first = regions[0]["bbox"]
    first_box = (first["x"], first["y"], first["width"], first["height"])
    draw.rectangle(
        (first_box[0], first_box[1], first_box[0] + first_box[2], first_box[1] + first_box[3]),
        fill=(169, 171, 161, 135),
        outline=(194, 194, 186, 130),
        width=4,
    )
    draw_centered_text(draw, first_box, regions[0]["expected_text"], weak_font, fill=(126, 124, 118))

    second = regions[1]["bbox"]
    second_box = (second["x"], second["y"], second["width"], second["height"])
    paste_angled_text(image, second_box, regions[1]["expected_text"], angled_font)

    third = regions[2]["bbox"]
    third_box = (third["x"], third["y"], third["width"], third["height"])
    draw.rectangle(
        (third_box[0], third_box[1], third_box[0] + third_box[2], third_box[1] + third_box[3]),
        outline=(238, 238, 230, 92),
        width=3,
    )
    draw_centered_text(draw, third_box, regions[2]["expected_text"], hard_font, fill=(215, 214, 206))

    rgb = image.convert("RGB")
    file_name = "synthetic_04_complex_background_skip.webp"
    rgb.save(output_dir / file_name, "WEBP", lossless=True, quality=100, method=6)
    return asset_manifest(file_name, rgb, ["complex_background", "weak_contrast", "angled_text", "skip_risk"], regions, output_dir)


GENERATORS: tuple[Callable[[Path, FontSet], dict[str, object]], ...] = (
    generate_clean_dialogue,
    generate_narration_boxes,
    generate_small_bubble_overflow,
    generate_complex_background_skip,
)


def generate_samples(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for file_name in GENERATED_FILE_NAMES:
        path = output_dir / file_name
        if path.exists():
            path.unlink()

    fonts = find_font_set()
    assets = [generator(output_dir, fonts) for generator in GENERATORS]
    manifest = {
        "version": "1.0",
        "generated_at": GENERATED_AT,
        "assets": assets,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic manga workflow samples.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated webp files and manifest.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = generate_samples(args.output_dir)
    print(f"Generated {len(manifest['assets'])} synthetic samples in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
