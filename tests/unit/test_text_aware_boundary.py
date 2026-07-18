from __future__ import annotations

import numpy as np
import pytest

from manga_read_flow.quality.text_aware_boundary import (
    TextAwareBoundaryInputs,
    correct_text_aware_virtual_boundary,
)


def test_guarded_required_support_relocates_only_virtual_uncertainty() -> None:
    s1, s2, virtual, visible, required, protected, uncertainty = _inputs()
    result = correct_text_aware_virtual_boundary(
        TextAwareBoundaryInputs(s2, s1, virtual, visible, required, protected, uncertainty),
        correction_ordinal=1,
    )
    assert result.status == "COMPLETE"
    assert result.unsafe_required_pixels == 0
    assert not (result.primary_instance & result.neighbor_instance).any()
    assert np.array_equal(result.primary_instance, s2)
    assert np.array_equal(result.neighbor_instance, s1)
    assert not (result.primary_safe_edit & (visible | protected | result.uncertainty)).any()
    assert result.budget_after == 0


def test_visible_or_protected_conflict_remains_blocked() -> None:
    s1, s2, virtual, visible, required, protected, uncertainty = _inputs()
    visible[5, 6] = True
    result = correct_text_aware_virtual_boundary(
        TextAwareBoundaryInputs(s2, s1, virtual, visible, required, protected, uncertainty),
        correction_ordinal=1,
    )
    assert result.status == "INCOMPLETE_REVIEW"
    assert result.reason_code == "guard_conflicts_visible_or_protected"
    assert result.unsafe_required_pixels > 0


def test_second_correction_is_rejected() -> None:
    s1, s2, virtual, visible, required, protected, uncertainty = _inputs()
    with pytest.raises(ValueError, match="ordinal 1"):
        correct_text_aware_virtual_boundary(
            TextAwareBoundaryInputs(s2, s1, virtual, visible, required, protected, uncertainty),
            correction_ordinal=2,
        )


def test_guard_margin_that_reaches_protected_structure_is_blocked() -> None:
    s1, s2, virtual, visible, required, protected, uncertainty = _inputs()
    protected[4, 8] = True
    result = correct_text_aware_virtual_boundary(
        TextAwareBoundaryInputs(
            s2, s1, virtual, visible, required, protected, uncertainty,
            guard_margin_px=2,
        ),
        correction_ordinal=1,
    )
    assert result.status == "INCOMPLETE_REVIEW"
    assert result.unsafe_required_pixels > 0


def _inputs():
    s1 = np.zeros((12, 12), dtype=bool); s1[:, :6] = True
    s2 = np.zeros((12, 12), dtype=bool); s2[:, 6:] = True
    virtual = np.zeros((12, 12), dtype=bool); virtual[:, 6] = True
    uncertainty = np.zeros((12, 12), dtype=bool); uncertainty[:, 6:8] = True
    visible = np.zeros((12, 12), dtype=bool)
    protected = np.zeros((12, 12), dtype=bool)
    required = np.zeros((12, 12), dtype=bool); required[4:8, 6:8] = True
    return s1, s2, virtual, visible, required, protected, uncertainty
