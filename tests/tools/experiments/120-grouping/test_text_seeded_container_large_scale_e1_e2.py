from pathlib import Path

from PIL import Image

from tools.experiments.grouping_120.text_seeded_container_association import large_scale_e1_e2_comparison as comparison


def test_book_pages_requires_exactly_forty_jpgs(tmp_path: Path):
    for index in range(40):
        Image.new("L", (3, 4), 255).save(tmp_path / f"_{index:03d}.jpg")
    assert len(comparison.book_pages(tmp_path)) == 40


def test_book_pages_stops_for_non_forty_page_input(tmp_path: Path):
    Image.new("L", (3, 4), 255).save(tmp_path / "_001.jpg")
    try:
        comparison.book_pages(tmp_path)
    except comparison.ComparisonStop as error:
        assert "expected 40 JPG pages" in str(error)
    else:  # pragma: no cover
        raise AssertionError("non-40-page input must stop")


def test_oversized_seed_is_resource_abstention():
    asset = {"width": 100, "height": 100, "fragments": [{"bbox": {"width": 11, "height": 100}}]}
    assert comparison.oversized_seed_reason(asset) == "oversized_fragment_seed"
