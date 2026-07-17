from pathlib import Path

import numpy as np
from PIL import ImageFont

from tools.spikes import typesetting_feasibility as typesetting


def _font(size=22):
    return ImageFont.truetype("DejaVuSans.ttf", size)


def test_wrap_preserves_text_and_obeys_forbidden_punctuation():
    text = "你好（这里不能乱换行），我们继续测试。"
    lines = typesetting.wrap_chinese(text, _font(), 90, 8)
    assert lines is not None
    assert "".join(lines) == text
    assert all(line[0] not in typesetting.FORBIDDEN_LINE_START for line in lines)
    assert all(line[-1] not in typesetting.FORBIDDEN_LINE_END for line in lines)


def test_mask_aware_layout_keeps_glyphs_inside_region():
    yy, xx = np.ogrid[:180, :180]
    region = (xx - 90) ** 2 / 78**2 + (yy - 90) ** 2 / 68**2 <= 1
    font_path = Path(ImageFont.truetype("DejaVuSans.ttf", 12).path)
    plan = typesetting.find_layout("c1", "自动排版可行性测试", region, font_path, min_size=10, max_size=30)
    assert plan is not None
    font = ImageFont.truetype(plan.font_path, plan.font_size)
    glyph = typesetting._glyph_mask(region.shape, plan.lines, plan.positions, font, plan.stroke_width)
    assert not np.any(glyph & ~region)
    assert plan.minimum_inner_margin >= 2.0
    assert plan.boundary_touch is False


def test_low_contrast_style_falls_back_to_black_or_white():
    source = np.full((20, 20, 3), 240, dtype=np.uint8)
    cleaned = source.copy()
    effective = np.zeros((20, 20), dtype=np.bool_)
    effective[5:10, 5:10] = True
    source[effective] = (225, 225, 225)
    region = np.ones((20, 20), dtype=np.bool_)
    foreground, _, ratio = typesetting.estimate_style(source, cleaned, effective, region)
    assert foreground == (0, 0, 0)
    assert ratio >= 4.5
