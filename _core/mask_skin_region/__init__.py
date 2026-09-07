"""mask.skin-region: human skin-region mask with an optional person gate.

The block owns all image preparation and mask postprocessing. Runtime model inference is isolated
behind two injected callables, so importing and testing this package needs only Torch and SciPy.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Callable

import torch
import torch.nn.functional as F

__all__ = [
    "SkinMaskError",
    "SkinMaskValidationError",
    "configure_factory_segmenters",
    "coverage_fraction",
    "execute_utility_operation",
]

_LOG = logging.getLogger("MATRIX.SkinMask")
_FLOAT_DTYPES = frozenset({torch.float16, torch.bfloat16, torch.float32, torch.float64})
_SEGMENT_PARTS: Callable[[torch.Tensor], Any] | None = None
_SEGMENT_PERSON: Callable[[torch.Tensor], Any] | None = None


class SkinMaskError(RuntimeError):
    """Base class for mask.skin-region failures."""


class SkinMaskValidationError(SkinMaskError, ValueError):
    """An input or injected model result violates the block contract."""


def configure_factory_segmenters(
    segment_parts: Callable[[torch.Tensor], Any],
    segment_person: Callable[[torch.Tensor], Any],
) -> None:
    """Install inference adapters for prepared HumanParts logits and person predictions.

    ``segment_parts`` receives float32 NHWC ``[1,512,512,3]`` normalized to ``[-1,1]`` and must
    return logits ``[1,512,512,20]``. ``segment_person`` receives ImageNet-normalized float32 NCHW
    ``[1,3,320,320]`` and must return the raw prediction ``[1,1,320,320]``.
    """
    if not callable(segment_parts) or not callable(segment_person):
        raise TypeError("factory skin segmenters must be callable")
    global _SEGMENT_PARTS, _SEGMENT_PERSON
    _SEGMENT_PARTS = segment_parts
    _SEGMENT_PERSON = segment_person


def coverage_fraction(mask: torch.Tensor) -> float:
    """Return the mean soft coverage of a finite MASK tensor."""
    if not isinstance(mask, torch.Tensor) or mask.ndim not in (2, 3) or mask.numel() == 0:
        raise SkinMaskValidationError("mask must be a non-empty [H,W] or [B,H,W] tensor")
    if mask.dtype not in _FLOAT_DTYPES or not bool(torch.isfinite(mask).all()):
        raise SkinMaskValidationError("mask must contain finite floating-point values")
    return float(mask.to(torch.float32).mean().item())


def _validate_image(image: Any) -> torch.Tensor:
    if not isinstance(image, torch.Tensor) or image.ndim != 4:
        raise SkinMaskValidationError("image must be an IMAGE tensor of shape [B,H,W,3 or 4]")
    if image.shape[-1] not in (3, 4):
        raise SkinMaskValidationError("image must have three RGB or four RGBA channels")
    if image.shape[0] < 1 or image.shape[1] < 1 or image.shape[2] < 1:
        raise SkinMaskValidationError("image must contain at least one frame and one pixel")
    if image.dtype not in _FLOAT_DTYPES:
        raise SkinMaskValidationError("image must use a floating-point dtype")
    if not bool(torch.isfinite(image).all()):
        raise SkinMaskValidationError("image must contain only finite values")
    if bool((image < 0).any()) or bool((image > 1).any()):
        raise SkinMaskValidationError("image values must lie within [0, 1]")
    return image


def _validate_widgets(item: dict[str, Any]) -> tuple[dict[str, bool], int, int, int, bool]:
    toggles: dict[str, bool] = {}
    for name in ("face", "torso", "arms", "legs"):
        value = item.get(name, True)
        if not isinstance(value, bool):
            raise SkinMaskValidationError(f"{name} must be BOOLEAN")
        toggles[name] = value
    feather = item.get("feather_px", 16)
    edge_radius = item.get("edge_radius_px", 8)
    expand = item.get("expand_px", 4)
    gate = item.get("person_gate", True)
    if isinstance(feather, bool) or not isinstance(feather, int) or not 0 <= feather <= 64:
        raise SkinMaskValidationError("feather_px must be an integer within 0..64")
    if (
        isinstance(edge_radius, bool)
        or not isinstance(edge_radius, int)
        or not 0 <= edge_radius <= 32
    ):
        raise SkinMaskValidationError("edge_radius_px must be an integer within 0..32")
    if isinstance(expand, bool) or not isinstance(expand, int) or not -32 <= expand <= 32:
        raise SkinMaskValidationError("expand_px must be an integer within -32..32")
    if not isinstance(gate, bool):
        raise SkinMaskValidationError("person_gate must be BOOLEAN")
    return toggles, feather, edge_radius, expand, gate


def _rgb_uint8_float(frame: torch.Tensor) -> torch.Tensor:
    return torch.round(frame[..., :3].to(torch.float32) * 255.0)


def _parts_mask(
    frame: torch.Tensor, toggles: dict[str, bool], segment_parts: Callable[[torch.Tensor], Any]
) -> torch.Tensor:
    height, width = frame.shape[:2]
    rgb = _rgb_uint8_float(frame).permute(2, 0, 1)[None]
    resized = F.interpolate(rgb, size=(512, 512), mode="bilinear", align_corners=False)
    prepared = (resized / 127.5 - 1.0).permute(0, 2, 3, 1).contiguous()
    try:
        raw = segment_parts(prepared)
        logits = torch.as_tensor(raw, device=frame.device)
    except Exception as exc:
        raise SkinMaskError(f"parts segmenter failed: {exc}") from exc
    if tuple(logits.shape) != (1, 512, 512, 20) or logits.dtype not in _FLOAT_DTYPES:
        raise SkinMaskValidationError("parts segmenter must return float logits [1,512,512,20]")
    if not bool(torch.isfinite(logits).all()):
        raise SkinMaskValidationError("parts segmenter returned non-finite logits")
    class_map = logits.argmax(dim=-1)[0]
    selected: list[int] = []
    if toggles["face"]:
        selected.append(13)
    if toggles["torso"]:
        selected.append(10)
    if toggles["arms"]:
        selected.extend((14, 15))
    if toggles["legs"]:
        selected.extend((16, 17))
    mask = torch.zeros_like(class_map, dtype=torch.bool)
    for class_index in selected:
        mask |= class_map == class_index
    return F.interpolate(
        mask.to(torch.float32)[None, None],
        size=(height, width),
        mode="bilinear",
        align_corners=False,
    )[0, 0].clamp_(0.0, 1.0)


def _person_mask(frame: torch.Tensor, segment_person: Callable[[torch.Tensor], Any]) -> torch.Tensor:
    height, width = frame.shape[:2]
    rgb = _rgb_uint8_float(frame).permute(2, 0, 1)[None]
    resized = F.interpolate(rgb, size=(320, 320), mode="bilinear", align_corners=False)
    scaled = resized / resized.max().clamp_min(1e-6)
    mean = torch.tensor((0.485, 0.456, 0.406), device=frame.device).view(1, 3, 1, 1)
    std = torch.tensor((0.229, 0.224, 0.225), device=frame.device).view(1, 3, 1, 1)
    prepared = ((scaled - mean) / std).to(torch.float32).contiguous()
    try:
        raw = segment_person(prepared)
        prediction = torch.as_tensor(raw, device=frame.device)
    except Exception as exc:
        raise SkinMaskError(f"person segmenter failed: {exc}") from exc
    if tuple(prediction.shape) != (1, 1, 320, 320) or prediction.dtype not in _FLOAT_DTYPES:
        raise SkinMaskValidationError("person segmenter must return float prediction [1,1,320,320]")
    if not bool(torch.isfinite(prediction).all()):
        raise SkinMaskValidationError("person segmenter returned a non-finite prediction")
    minimum = prediction.amin()
    span = prediction.amax() - minimum
    if float(span) <= 0.0:
        normalized = torch.zeros_like(prediction, dtype=torch.float32)
    else:
        normalized = (prediction.to(torch.float32) - minimum) / span
    return F.interpolate(
        normalized,
        size=(height, width),
        mode="bilinear",
        align_corners=False,
    )[0, 0].clamp_(0.0, 1.0)


def _cross_morphology(mask: torch.Tensor, amount: int) -> torch.Tensor:
    result = mask
    reducer = torch.maximum if amount > 0 else torch.minimum
    pad_value = 0.0 if amount > 0 else 1.0
    for _ in range(abs(amount)):
        padded = F.pad(result[None, None], (1, 1, 1, 1), value=pad_value)[0, 0]
        candidates = (
            padded[1:-1, 1:-1],
            padded[:-2, 1:-1],
            padded[2:, 1:-1],
            padded[1:-1, :-2],
            padded[1:-1, 2:],
        )
        result = candidates[0]
        for candidate in candidates[1:]:
            result = reducer(result, candidate)
    return result


def _fill_holes(mask: torch.Tensor) -> torch.Tensor:
    import scipy.ndimage

    binary = mask.detach().to(device="cpu", dtype=torch.bool).numpy()
    all_filled = scipy.ndimage.binary_fill_holes(binary)
    holes = all_filled & ~binary
    labels, count = scipy.ndimage.label(holes)
    maximum_area = int(math.floor(binary.size * 0.02))
    accepted = binary.copy()
    if count and maximum_area:
        areas = scipy.ndimage.sum(holes, labels, range(1, count + 1))
        for label, area in enumerate(areas, start=1):
            if area <= maximum_area:
                accepted[labels == label] = True
    return torch.as_tensor(accepted, dtype=torch.float32, device=mask.device)


def _reflection_indices(length: int, radius: int, device: torch.device) -> torch.Tensor:
    if length == 1:
        return torch.zeros(length + 2 * radius, dtype=torch.long, device=device)
    positions = torch.arange(-radius, length + radius, device=device)
    period = 2 * (length - 1)
    folded = torch.remainder(positions, period)
    return torch.where(folded < length, folded, period - folded).to(torch.long)


def _gaussian_kernel(sigma: int, device: torch.device) -> torch.Tensor:
    radius = 3 * sigma
    offsets = torch.arange(-radius, radius + 1, dtype=torch.float32, device=device)
    kernel = torch.exp(-(offsets * offsets) / (2.0 * float(sigma * sigma)))
    return kernel / kernel.sum()


def _gaussian_feather(mask: torch.Tensor, sigma: int) -> torch.Tensor:
    if sigma == 0:
        return mask
    radius = 3 * sigma
    kernel = _gaussian_kernel(sigma, mask.device)
    work = mask.to(torch.float32)[None, None]
    x_index = _reflection_indices(mask.shape[1], radius, mask.device)
    work = work.index_select(3, x_index)
    work = F.conv2d(work, kernel.view(1, 1, 1, -1))
    y_index = _reflection_indices(mask.shape[0], radius, mask.device)
    work = work.index_select(2, y_index)
    work = F.conv2d(work, kernel.view(1, 1, -1, 1))
    return work[0, 0].clamp_(0.0, 1.0)


def _box_filter(value: torch.Tensor, radius: int) -> torch.Tensor:
    if radius == 0:
        return value
    y_index = _reflection_indices(value.shape[0], radius, value.device)
    x_index = _reflection_indices(value.shape[1], radius, value.device)
    padded = value.index_select(0, y_index).index_select(1, x_index)[None, None]
    size = 2 * radius + 1
    return F.avg_pool2d(padded, kernel_size=size, stride=1)[0, 0]


def _guided_filter(
    mask: torch.Tensor, luminance: torch.Tensor, radius: int, epsilon: float = 1e-3
) -> torch.Tensor:
    if radius == 0:
        return mask
    guide = luminance.to(torch.float32)
    source = mask.to(torch.float32)
    mean_guide = _box_filter(guide, radius)
    mean_source = _box_filter(source, radius)
    covariance = _box_filter(guide * source, radius) - mean_guide * mean_source
    variance = _box_filter(guide * guide, radius) - mean_guide * mean_guide
    a = covariance / (variance + epsilon)
    b = mean_source - a * mean_guide
    refined = _box_filter(a, radius) * guide + _box_filter(b, radius)
    return refined.clamp_(0.0, 1.0)


def execute_utility_operation(item: dict[str, Any]) -> tuple[torch.Tensor, torch.Tensor]:
    """Execute the compiled MATRIX_SkinMask operation for one IMAGE batch."""
    if not isinstance(item, dict):
        raise SkinMaskValidationError("mask.skin-region requires an input mapping")
    if "image" not in item:
        raise SkinMaskValidationError("missing skin mask input: image")
    if _SEGMENT_PARTS is None or _SEGMENT_PERSON is None:
        raise SkinMaskValidationError(
            "mask.skin-region runtime segmenters are not configured by the pack bootstrap"
        )
    image = _validate_image(item["image"])
    toggles, feather, edge_radius, expand, use_gate = _validate_widgets(item)
    masks: list[torch.Tensor] = []
    for index, frame in enumerate(image):
        soft = _parts_mask(frame, toggles, _SEGMENT_PARTS)
        if use_gate:
            soft = (soft * _person_mask(frame, _SEGMENT_PERSON)).clamp_(0.0, 1.0)
        binary = soft >= 0.5
        filled_binary = _fill_holes(binary)
        has_soft_confidence = bool(((soft > 0.0) & (soft < 1.0)).any())
        if has_soft_confidence:
            soft_local = _cross_morphology(soft, abs(expand))
        else:
            # A hard source has no confidence gradient to inherit; retain historical hard fills.
            soft_local = filled_binary
        mask = torch.maximum(soft, filled_binary * soft_local)
        mask = _cross_morphology(mask, expand)
        luminance = (
            frame[..., 0].to(torch.float32) * 0.2126
            + frame[..., 1].to(torch.float32) * 0.7152
            + frame[..., 2].to(torch.float32) * 0.0722
        )
        mask = _guided_filter(mask, luminance, edge_radius)
        mask = _gaussian_feather(mask, feather).to(torch.float32)
        _LOG.info("frame %d coverage=%.6f", index, coverage_fraction(mask))
        masks.append(mask)
    output = torch.stack(masks).to(device=image.device, dtype=torch.float32)
    preview = output[..., None].expand(-1, -1, -1, 3).clone()
    return output, preview
