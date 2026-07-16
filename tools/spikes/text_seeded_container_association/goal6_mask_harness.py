#!/usr/bin/env python3
"""Goal 6 local Pixel Text Mask and safe-edit harness.

This module intentionally has no product integration.  It treats Goal 5 spatial
regions as upper bounds, never as deletion masks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


class Goal6Stop(RuntimeError):
    """Raised when a Goal 6 safety contract cannot be satisfied."""


@dataclass(frozen=True)
class Fragment:
    fragment_id: str
    polygon: tuple[tuple[float, float], ...]
    score: float | None = None


@dataclass(frozen=True)
class Context:
    region_id: str
    fragment_ids: tuple[str, ...]
    mask: np.ndarray


@dataclass(frozen=True)
class MaskPolicy:
    threshold_bias: int
    soft_radius: int
    contour_band_px: int
    structure_quantile: float
    min_component_area: int = 2
    max_component_fraction: float = 0.12
    e1_min_luminance: float = 220.0
    e1_max_stddev: float = 36.0
    soft_edge_completion_radius: int = 0
    soft_edge_completion_max_luminance: int = 250

    def __post_init__(self) -> None:
        if self.soft_radius < 1 or self.contour_band_px < 1:
            raise Goal6Stop("mask radii must be positive")
        if not 0.5 <= self.structure_quantile < 1.0:
            raise Goal6Stop("invalid structure quantile")
        if not 0 <= self.soft_edge_completion_radius <= 3:
            raise Goal6Stop("soft-edge completion radius must be in [0, 3]")
        if not 1 <= self.soft_edge_completion_max_luminance < 255:
            raise Goal6Stop("invalid soft-edge completion luminance")


@dataclass(frozen=True)
class ContextResult:
    context_id: str
    fragment_status: dict[str, str]
    seed: np.ndarray
    core: np.ndarray
    soft: np.ndarray
    uncertain: np.ndarray
    protected: np.ndarray
    safe: np.ndarray
    effective: np.ndarray
    risk: str
    decision: str
    diagnostics: dict[str, float | int | bool]


def _image_mask(mask: np.ndarray) -> Image.Image:
    return Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L")


def dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    return np.asarray(_image_mask(mask).filter(ImageFilter.MaxFilter(radius * 2 + 1))) > 0


def erode(mask: np.ndarray, radius: int) -> np.ndarray:
    return np.asarray(_image_mask(mask).filter(ImageFilter.MinFilter(radius * 2 + 1))) > 0


def boundary(mask: np.ndarray, radius: int = 1) -> np.ndarray:
    return mask & ~erode(mask, radius)


def polygon_mask(shape: tuple[int, int], fragments: Iterable[Fragment]) -> np.ndarray:
    image = Image.new("L", (shape[1], shape[0]), 0)
    draw = ImageDraw.Draw(image)
    for fragment in fragments:
        if len(fragment.polygon) >= 3:
            draw.polygon(list(fragment.polygon), fill=255)
    return np.asarray(image) > 0


def rle_to_mask(payload: dict) -> np.ndarray:
    height, width = payload["shape"]
    values: list[bool] = []
    value = bool(payload["starts_with"])
    for count in payload["counts"]:
        values.extend([value] * int(count))
        value = not value
    if len(values) != height * width:
        raise Goal6Stop("invalid Goal 5 mask RLE")
    return np.asarray(values, dtype=np.bool_).reshape((height, width))


def luminance(image: np.ndarray) -> np.ndarray:
    if image.ndim != 3 or image.shape[2] != 3:
        raise Goal6Stop("image must be RGB")
    return (0.2126 * image[..., 0] + 0.7152 * image[..., 1] + 0.0722 * image[..., 2]).astype(np.uint8)


def otsu_threshold(values: np.ndarray) -> int:
    if values.size == 0:
        raise Goal6Stop("cannot threshold empty context")
    hist = np.bincount(values.astype(np.uint8), minlength=256).astype(np.float64)
    probability = hist / hist.sum()
    omega = np.cumsum(probability)
    mu = np.cumsum(probability * np.arange(256))
    mu_total = mu[-1]
    denominator = omega * (1.0 - omega)
    score = np.divide((mu_total * omega - mu) ** 2, denominator, out=np.zeros_like(mu), where=denominator > 0)
    return int(np.argmax(score))


def _components(mask: np.ndarray) -> list[np.ndarray]:
    """8-connected components, sized for the small local Goal 6 crops."""
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=np.bool_)
    result: list[np.ndarray] = []
    for y, x in np.argwhere(mask):
        if seen[y, x]:
            continue
        stack = [(int(y), int(x))]
        seen[y, x] = True
        pixels: list[tuple[int, int]] = []
        while stack:
            cy, cx = stack.pop()
            pixels.append((cy, cx))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        component = np.zeros_like(mask, dtype=np.bool_)
        ys, xs = zip(*pixels)
        component[np.asarray(ys), np.asarray(xs)] = True
        result.append(component)
    return result


def _gradient(gray: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(gray.astype(np.float32))
    return np.hypot(gx, gy)


def _fragment_status(seed: np.ndarray, core: np.ndarray, fragments: Iterable[Fragment]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for fragment in fragments:
        fragment_seed = polygon_mask(seed.shape, (fragment,))
        statuses[fragment.fragment_id] = "assigned_core" if np.any(core & dilate(fragment_seed, 2)) else "unassigned_with_reason"
    return statuses


def process_context(
    image: np.ndarray,
    context: Context,
    fragments: Iterable[Fragment],
    route: str,
    policy: MaskPolicy,
    neighbor_contexts: Iterable[np.ndarray] = (),
) -> ContextResult:
    if context.mask.dtype != np.bool_ or context.mask.shape != image.shape[:2] or not context.mask.any():
        raise Goal6Stop("invalid context mask")
    owned = tuple(item for item in fragments if item.fragment_id in context.fragment_ids)
    if not owned:
        raise Goal6Stop("context has no traceable fragments")
    seed = polygon_mask(context.mask.shape, owned) & context.mask
    if not seed.any():
        raise Goal6Stop("fragment polygons do not intersect context")
    gray = luminance(image)
    threshold = int(np.clip(otsu_threshold(gray[context.mask]) + policy.threshold_bias, 0, 255))
    dark = (gray <= threshold) & context.mask
    expanded_seed = dilate(seed, 2) & context.mask
    core = np.zeros_like(context.mask)
    max_area = max(1, int(context.mask.sum() * policy.max_component_fraction))
    context_border = boundary(context.mask, 1)
    for component in _components(dark):
        area = int(component.sum())
        if policy.min_component_area <= area <= max_area and np.any(component & expanded_seed) and not np.any(component & context_border):
            core |= component
    contour = boundary(context.mask, policy.contour_band_px)
    gradient = _gradient(gray)
    non_seed = context.mask & ~dilate(seed, policy.soft_radius + 1)
    structure = np.zeros_like(context.mask)
    if np.any(non_seed):
        threshold_gradient = float(np.quantile(gradient[non_seed], policy.structure_quantile))
        structure = (gradient >= threshold_gradient) & non_seed
        structure = dilate(structure, 1) & context.mask
    neighbor_band = np.zeros_like(context.mask)
    for neighbor in neighbor_contexts:
        neighbor_band |= dilate(neighbor, policy.contour_band_px) & context.mask
    intrinsic_protected = contour | structure | neighbor_band
    hard_core = core.copy()
    completed = np.zeros_like(core)
    if policy.soft_edge_completion_radius:
        candidate_edge = (
            dilate(hard_core, policy.soft_edge_completion_radius)
            & seed
            & context.mask
            & ~intrinsic_protected
            & (gray > threshold)
            & (gray <= policy.soft_edge_completion_max_luminance)
        )
        completed = candidate_edge & ~hard_core
        core |= completed
    soft = dilate(core, policy.soft_radius) & context.mask
    uncertain = soft & ~core
    protected = intrinsic_protected | uncertain
    safe = context.mask & ~protected
    effective = core & safe
    statuses = _fragment_status(seed, core, owned)
    unassigned = sum(value != "assigned_core" for value in statuses.values())
    background = context.mask & ~soft
    mean = float(np.mean(gray[background])) if np.any(background) else 0.0
    stddev = float(np.std(gray[background])) if np.any(background) else float("inf")
    geometry_safe = bool(effective.any() and not np.any(core & protected) and unassigned == 0)
    if not geometry_safe:
        risk, decision = "E3", "SKIP"
    elif route == "BOUNDED_SUPPORT":
        risk, decision = "E3", "REVIEW_REQUIRED"
    elif mean >= policy.e1_min_luminance and stddev <= policy.e1_max_stddev:
        risk, decision = "E1", "REVIEW_REQUIRED"
    else:
        risk, decision = "E2", "REVIEW_REQUIRED"
    return ContextResult(
        context.region_id,
        statuses,
        seed,
        core,
        soft,
        uncertain,
        protected,
        safe,
        effective,
        risk,
        decision,
        {
            "context_pixels": int(context.mask.sum()),
            "hard_core_pixels": int(hard_core.sum()),
            "soft_edge_completed_pixels": int(completed.sum()),
            "core_pixels": int(core.sum()),
            "effective_pixels": int(effective.sum()),
            "protected_overlap_pixels": int((effective & protected).sum()),
            "threshold": threshold,
            "background_luminance": mean,
            "background_stddev": stddev,
            "unassigned_fragment_count": unassigned,
        },
    )


def verify_disjoint(results: Iterable[ContextResult]) -> None:
    seen: np.ndarray | None = None
    for result in results:
        if seen is None:
            seen = np.zeros_like(result.effective)
        if np.any(seen & result.effective):
            raise Goal6Stop("effective masks cross container boundaries")
        seen |= result.effective


def fixed_white(image: np.ndarray, effective: np.ndarray) -> np.ndarray:
    output = image.copy()
    output[effective] = (255, 255, 255)
    return output


def border_sampled_fill(image: np.ndarray, effective: np.ndarray, safe: np.ndarray, soft: np.ndarray) -> np.ndarray:
    ring = dilate(effective, 4) & safe & ~dilate(soft, 1)
    if not np.any(ring):
        raise Goal6Stop("no safe border-sampling ring")
    color = np.median(image[ring], axis=0).astype(np.uint8)
    output = image.copy()
    output[effective] = color
    return output


def low_radius_telea(image: np.ndarray, effective: np.ndarray, radius: int = 2) -> np.ndarray:
    """E2-only, local comparison candidate; never a product inpainting path."""
    if radius != 2:
        raise Goal6Stop("Goal 6 freezes the E2 Telea comparison radius at 2")
    if effective.dtype != np.bool_ or effective.shape != image.shape[:2] or not effective.any():
        raise Goal6Stop("invalid E2 Telea effective mask")
    try:
        import cv2
    except ImportError as error:  # pragma: no cover - dependency is asserted by the E2 harness run.
        raise Goal6Stop("OpenCV is required for the permitted E2 Telea comparison") from error
    bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    inpainted = cv2.inpaint(bgr, effective.astype(np.uint8) * 255, float(radius), cv2.INPAINT_TELEA)
    output = cv2.cvtColor(inpainted, cv2.COLOR_BGR2RGB)
    if changed_outside(image, output, effective) != 0:
        raise Goal6Stop("E2 Telea modified pixels outside M_effective")
    return output


def changed_outside(before: np.ndarray, after: np.ndarray, effective: np.ndarray) -> int:
    changed = np.any(before != after, axis=2)
    return int((changed & ~effective).sum())
