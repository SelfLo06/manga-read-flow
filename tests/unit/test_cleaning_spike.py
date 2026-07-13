from __future__ import annotations

import importlib.util
from pathlib import Path

import cv2
import numpy as np
import pytest


MODULE_PATH = Path(__file__).parents[2] / "tools" / "spikes" / "cleaning" / "spike.py"
SPEC = importlib.util.spec_from_file_location("cleaning_spike", MODULE_PATH)
assert SPEC and SPEC.loader
spike = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(spike)


def test_path_traversal_is_rejected() -> None:
    with pytest.raises(ValueError, match="escapes repository"):
        spike.inside_root(Path("/tmp/outside-cleaning-spike"))


def test_dilation_is_fixed_and_monotonic() -> None:
    mask = np.zeros((9, 9), dtype=np.uint8)
    mask[4, 4] = 255
    assert np.array_equal(spike.dilate(mask, 0), mask)
    assert int((spike.dilate(mask, 1) > 0).sum()) == 9
    assert int((spike.dilate(mask, 2) > 0).sum()) == 25


def test_fixed_white_changes_only_inside_mask() -> None:
    source = np.full((5, 5, 3), 17, dtype=np.uint8)
    mask = np.zeros((5, 5), dtype=np.uint8)
    mask[2, 2] = 255
    output = spike.clean(source, mask, "fixed_white", None)
    assert np.array_equal(output[mask == 0], source[mask == 0])
    assert output[2, 2].tolist() == [255, 255, 255]


def test_border_sampled_fill_uses_local_ring() -> None:
    source = np.full((9, 9, 3), (12, 23, 34), dtype=np.uint8)
    source[4, 4] = (0, 0, 0)
    mask = np.zeros((9, 9), dtype=np.uint8)
    mask[4, 4] = 255
    output = spike.clean(source, mask, "border_sampled_fill", None)
    assert output[4, 4].tolist() == [12, 23, 34]


@pytest.mark.parametrize("method", ["telea", "navier_stokes"])
def test_inpaint_preserves_output_dimensions(method: str) -> None:
    source = np.full((32, 32, 3), 200, dtype=np.uint8)
    cv2.line(source, (0, 16), (31, 16), (20, 20, 20), 1)
    mask = np.zeros((32, 32), dtype=np.uint8)
    mask[13:19, 13:19] = 255
    output = spike.clean(source, mask, method, 3)
    assert output.shape == source.shape


def test_outside_mask_metric_detects_changed_pixel() -> None:
    source = np.zeros((5, 5, 3), dtype=np.uint8)
    output = source.copy()
    output[2, 2] = (255, 255, 255)
    output[0, 0] = (255, 255, 255)
    mask = np.zeros((5, 5), dtype=np.uint8)
    mask[2, 2] = 255
    report = spike.metrics(source, output, mask)
    assert report["changed_inside_mask"] == 1
    assert report["changed_outside_mask"] == 1
    assert report["outside_mask_change_ratio"] > 0


def test_invalid_method_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported method"):
        spike.clean(np.zeros((2, 2, 3), dtype=np.uint8), np.zeros((2, 2), dtype=np.uint8), "lama", 3)


def test_candidate_id_includes_all_frozen_parameters() -> None:
    assert spike.candidate_id("f", "telea", 5, 2) == "f__telea__r5__d2"
    assert spike.candidate_id("f", "fixed_white", None, 1) == "f__fixed_white__rna__d1"
