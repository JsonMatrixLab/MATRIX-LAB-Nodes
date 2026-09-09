"""mask.eye-region: deterministic eye-region masks behind injected inference seams."""

from __future__ import annotations

import logging
import math
from typing import Any, Callable

import torch
import torch.nn.functional as F

__all__ = [
    "DETECTOR_IDS",
    "EyeMaskError",
    "EyeMaskValidationError",
    "configure_factory_eye_seams",
    "execute_utility_operation",
    "eye_mask",
]

_LOG = logging.getLogger("MATRIX.EyeMask")
DETECTOR_IDS = (
    "bbox/Eyeful_v2-Individual.pt",
)
_FLOAT_DTYPES = frozenset({torch.float16, torch.bfloat16, torch.float32, torch.float64})


class EyeMaskError(RuntimeError):
    """Base class for mask.eye-region failures."""


class EyeMaskValidationError(EyeMaskError, ValueError):
    """An input violates the contract before inference."""


def _exact_int(name: str, value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise EyeMaskValidationError(f"{name} must be an integer within {minimum}..{maximum}")
    return value


def _validate_inputs(
    image: Any,
    detector: Any,
    resolution: Any,
    threshold: Any,
    min_size_px: Any,
    max_eyes: Any,
    sam_refine: Any,
    feather_px: Any,
    sam_erosion_px: Any,
) -> tuple[torch.Tensor, float, int, int, int, int]:
    if not isinstance(image, torch.Tensor) or image.ndim != 4:
        raise EyeMaskValidationError("image must be an IMAGE tensor with rank 4 [B,H,W,C]")
    if image.dtype not in _FLOAT_DTYPES:
        raise EyeMaskValidationError("image must have a floating-point dtype")
    if image.shape[0] < 1 or image.shape[1] < 1 or image.shape[2] < 1:
        raise EyeMaskValidationError("image must contain at least one frame and one pixel")
    if image.shape[0] != 1:
        raise EyeMaskValidationError(
            "image must contain exactly one frame; the Factory map policy slices IMAGE batches"
        )
    if image.shape[3] not in (3, 4):
        raise EyeMaskValidationError("image must have 3 or 4 channels")
    if not bool(torch.isfinite(image).all()) or bool((image < 0).any()) or bool((image > 1).any()):
        raise EyeMaskValidationError("image values must be finite and lie within [0, 1]")
    if detector not in DETECTOR_IDS:
        raise EyeMaskValidationError(f"unknown detector id {detector!r}")
    resolution = _exact_int("resolution", resolution, 64, 4096)
    min_size_px = _exact_int("min_size_px", min_size_px, 1, 1024)
    max_eyes = _exact_int("max_eyes", max_eyes, 1, 8)
    feather_px = _exact_int("feather_px", feather_px, 0, 64)
    sam_erosion_px = _exact_int("sam_erosion_px", sam_erosion_px, 0, 32)
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise EyeMaskValidationError("threshold must be a number within 0.05..0.95")
    threshold = float(threshold)
    if not math.isfinite(threshold) or not 0.05 <= threshold <= 0.95:
        raise EyeMaskValidationError("threshold must be finite and within 0.05..0.95")
    if not isinstance(sam_refine, bool):
        raise EyeMaskValidationError("sam_refine must be a boolean")
    return image, threshold, resolution, min_size_px, max_eyes, sam_erosion_px


def _empty(height: int, width: int, device: torch.device):
    union = torch.zeros((1, height, width), dtype=torch.float32, device=device)
    # MASK sockets may not carry a zero-length batch. A single all-zero item represents
    # the legitimate "no accepted eyes" result; the empty BBOX list remains the count.
    masks = torch.zeros((1, height, width), dtype=torch.float32, device=device)
    preview = torch.zeros((1, height, width, 3), dtype=torch.float32, device=device)
    return union, masks, [], preview


def _parse_detections(
    raw: Any, *, height: int, width: int, threshold: float, min_size_px: int, max_eyes: int
) -> list[tuple[int, int, int, int]]:
    if not isinstance(raw, (tuple, list)) or len(raw) != 3:
        raise EyeMaskError("detector must return (xyxy, conf, cls)")
    boxes = torch.as_tensor(raw[0], dtype=torch.float32, device="cpu")
    scores = torch.as_tensor(raw[1], dtype=torch.float32, device="cpu")
    classes = torch.as_tensor(raw[2], device="cpu")
    if boxes.numel() == 0:
        boxes = boxes.reshape(0, 4)
    if boxes.ndim != 2 or boxes.shape[1] != 4:
        raise EyeMaskError("detector xyxy must have shape [N,4]")
    count = boxes.shape[0]
    if scores.ndim != 1 or classes.ndim != 1 or scores.shape[0] != count or classes.shape[0] != count:
        raise EyeMaskError("detector conf and cls must have shape [N]")
    if count and (classes.dtype == torch.bool or classes.dtype.is_floating_point or classes.dtype.is_complex):
        raise EyeMaskError("detector cls must contain integers")
    if not bool(torch.isfinite(boxes).all()) or not bool(torch.isfinite(scores).all()):
        raise EyeMaskError("detector coordinates and confidence must be finite")
    if bool((scores < 0).any()) or bool((scores > 1).any()):
        raise EyeMaskError("detector confidence must lie within [0, 1]")

    clamped = boxes.clone()
    clamped[:, (0, 2)] = clamped[:, (0, 2)].clamp(0, width)
    clamped[:, (1, 3)] = clamped[:, (1, 3)].clamp(0, height)
    candidates: list[tuple[float, int, tuple[int, int, int, int]]] = []
    for index in range(count):
        score = float(scores[index])
        if score < threshold:
            continue
        x0f, y0f, x1f, y1f = (float(value) for value in clamped[index])
        if x1f - x0f < min_size_px or y1f - y0f < min_size_px:
            continue
        box = (
            max(0, min(width, math.floor(x0f))),
            max(0, min(height, math.floor(y0f))),
            max(0, min(width, math.ceil(x1f))),
            max(0, min(height, math.ceil(y1f))),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        candidates.append((score, index, box))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    retained = candidates[:max_eyes]
    retained.sort(
        key=lambda item: (
            (item[2][0] + item[2][2]) / 2,
            (item[2][1] + item[2][3]) / 2,
            item[1],
        )
    )
    return [item[2] for item in retained]


def _rectangle(box: tuple[int, int, int, int], height: int, width: int) -> torch.Tensor:
    mask = torch.zeros((height, width), dtype=torch.float32)
    x0, y0, x1, y1 = box
    mask[y0:y1, x0:x1] = 1.0
    return mask


def _erode(mask: torch.Tensor, size: int) -> torch.Tensor:
    if size == 0:
        return mask
    # Match OpenCV's default anchor floor(size / 2), including its asymmetric even kernel.
    before = size // 2
    after = size - before - 1
    padded = F.pad(mask[None, None], (before, after, before, after), mode="constant", value=1.0)
    return -F.max_pool2d(-padded, kernel_size=size, stride=1)[0, 0]


def _reflect_indices(length: int, radius: int, device: torch.device) -> torch.Tensor:
    if length == 1:
        return torch.zeros(length + 2 * radius, dtype=torch.long, device=device)
    values = torch.arange(-radius, length + radius, device=device)
    period = 2 * length - 2
    folded = torch.remainder(values, period)
    return torch.where(folded < length, folded, period - folded).to(torch.long)


def _feather(mask: torch.Tensor, radius: int) -> torch.Tensor:
    if radius == 0:
        return mask.clone()
    axis = torch.arange(-radius, radius + 1, dtype=torch.float32)
    kernel = torch.exp(-(axis * axis) / (2.0 * float(radius) ** 2))
    kernel /= kernel.sum()
    y_index = _reflect_indices(mask.shape[0], radius, mask.device)
    x_index = _reflect_indices(mask.shape[1], radius, mask.device)
    padded = mask.index_select(0, y_index).index_select(1, x_index)[None, None]
    horizontal = F.conv2d(padded, kernel.reshape(1, 1, 1, -1))
    blurred = F.conv2d(horizontal, kernel.reshape(1, 1, -1, 1))[0, 0]
    return blurred.clamp(0.0, 1.0)


def _eye_mask_impl(
    image: torch.Tensor,
    *,
    detector: str = DETECTOR_IDS[0],
    resolution: int = 1280,
    threshold: float = 0.5,
    min_size_px: int = 24,
    max_eyes: int = 2,
    sam_refine: bool = True,
    feather_px: int = 6,
    sam_erosion_px: int = 10,
    detect: Callable[..., Any],
    refine: Callable[..., Any],
) -> tuple[torch.Tensor, torch.Tensor, list[tuple[int, int, int, int]], torch.Tensor]:
    """Detect eyes in one frame and return union, per-eye masks, boxes, and preview."""
    image, threshold, resolution, min_size_px, max_eyes, sam_erosion_px = _validate_inputs(
        image, detector, resolution, threshold, min_size_px, max_eyes, sam_refine, feather_px,
        sam_erosion_px,
    )
    if not callable(detect) or not callable(refine):
        raise EyeMaskValidationError("detect and refine seams must be callable")
    height, width = image.shape[1:3]
    rgb = (
        image[0, :, :, :3].detach().to(device="cpu", dtype=torch.float32).clone().mul(255.0)
        .round().clamp(0, 255).to(torch.uint8).numpy()
    )
    try:
        raw = detect(detector, rgb, conf=threshold, imgsz=resolution)
    except ModuleNotFoundError as error:
        raise EyeMaskError(
            f"eye detector runtime package is missing ({error}); install the configured detector runtime"
        ) from error
    except (FileNotFoundError, KeyError) as error:
        raise EyeMaskError(
            f"eye detector asset {detector!r} is missing or unregistered ({error}); install/register the asset"
        ) from error
    except Exception as error:
        raise EyeMaskError(f"eye detector inference failed: {error}") from error

    boxes = _parse_detections(
        raw, height=height, width=width, threshold=threshold,
        min_size_px=min_size_px, max_eyes=max_eyes,
    )
    if not boxes:
        _LOG.warning("no accepted eye detections; returning empty outputs")
        return _empty(height, width, image.device)
    masks: list[torch.Tensor] = []
    refined_boxes: list[tuple[int, int, int, int]] = []
    for box in boxes:
        if sam_refine:
            box_array = torch.tensor(box, dtype=torch.float32).numpy()
            point_array = torch.tensor(
                [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2], dtype=torch.float32
            ).numpy()
            try:
                refined = torch.as_tensor(refine(rgb, box_array, point_array), device="cpu")
            except ModuleNotFoundError as error:
                raise EyeMaskError(
                    f"SAM runtime package is missing ({error}); install the configured SAM runtime"
                ) from error
            except (FileNotFoundError, KeyError) as error:
                raise EyeMaskError(
                    f"SAM asset is missing or unregistered ({error}); install/register the configured asset"
                ) from error
            except EyeMaskError:
                raise
            except Exception as error:
                raise EyeMaskError(f"SAM refinement failed for box {box}: {error}") from error
            if refined.shape != (height, width):
                raise EyeMaskError(
                    f"SAM refine mask has shape {tuple(refined.shape)}, expected {(height, width)}"
                )
            if refined.dtype == torch.bool:
                refined = refined.to(torch.float32)
            elif refined.dtype not in _FLOAT_DTYPES:
                raise EyeMaskError("SAM refine mask must be boolean or floating point")
            else:
                refined = refined.to(torch.float32)
            if not bool(torch.isfinite(refined).all()) or bool((refined < 0).any()) or bool((refined > 1).any()):
                raise EyeMaskError("SAM refine mask must be finite and within [0, 1]")
            refined = (refined >= 0.5).to(torch.float32)
            if not bool(refined.any()):
                _LOG.warning("eye refinement skipped: SAM returned an empty mask for box %s", box)
                continue
            current = _erode(refined, sam_erosion_px)
            if not bool(current.any()):
                _LOG.warning(
                    "eye refinement skipped: erosion emptied mask for box %s; reduce sam_erosion_px",
                    box,
                )
                continue
        else:
            current = _rectangle(box, height, width)
        masks.append(_feather(current, feather_px))
        refined_boxes.append(box)
    if not masks:
        return _empty(height, width, image.device)
    stacked = torch.stack(masks).to(dtype=torch.float32, device=image.device).clamp(0, 1)
    union = stacked.amax(dim=0, keepdim=True)
    preview = union.unsqueeze(-1).expand(-1, -1, -1, 3).clone()
    return union, stacked, refined_boxes, preview


def eye_mask(
    image: torch.Tensor,
    *,
    detector: str = DETECTOR_IDS[0],
    resolution: int = 1280,
    threshold: float = 0.5,
    min_size_px: int = 24,
    max_eyes: int = 2,
    sam_refine: bool = True,
    feather_px: int = 6,
    sam_erosion_px: int = 10,
    detect: Callable[..., Any],
    refine: Callable[..., Any],
) -> tuple[torch.Tensor, torch.Tensor, list[tuple[int, int, int, int]], torch.Tensor]:
    """Run eye masking while preserving validation errors and normalizing runtime failures."""
    try:
        return _eye_mask_impl(
            image,
            detector=detector,
            resolution=resolution,
            threshold=threshold,
            min_size_px=min_size_px,
            max_eyes=max_eyes,
            sam_refine=sam_refine,
            feather_px=feather_px,
            sam_erosion_px=sam_erosion_px,
            detect=detect,
            refine=refine,
        )
    except (EyeMaskValidationError, EyeMaskError):
        raise
    except Exception as error:
        raise EyeMaskError(f"eye mask processing failed: {error}") from error


_DETECT: Callable[..., Any] | None = None
_REFINE: Callable[..., Any] | None = None


def configure_factory_eye_seams(detect: Callable[..., Any], refine: Callable[..., Any]) -> None:
    """Install detector and per-eye SAM callables supplied by the compiled bootstrap."""
    if not callable(detect) or not callable(refine):
        raise TypeError("factory eye seams must be callable")
    global _DETECT, _REFINE
    _DETECT, _REFINE = detect, refine


def execute_utility_operation(item: dict) -> tuple:
    """Factory seam for the compiled MATRIX_EyeMask node."""
    if not isinstance(item, dict):
        raise EyeMaskValidationError("mask.eye-region requires an input mapping")
    if "image" not in item:
        raise EyeMaskValidationError("missing required image input")
    if _DETECT is None or _REFINE is None:
        raise EyeMaskError(
            "mask.eye-region runtime seams are not configured; initialize detector and SAM seams"
        )
    return eye_mask(
        item["image"],
        detector=item.get("detector", DETECTOR_IDS[0]),
        resolution=item.get("resolution", 1280),
        threshold=item.get("threshold", 0.5),
        min_size_px=item.get("min_size_px", 24),
        max_eyes=item.get("max_eyes", 2),
        sam_refine=item.get("sam_refine", True),
        feather_px=item.get("feather_px", 6),
        sam_erosion_px=item.get("sam_erosion_px", 10),
        detect=_DETECT,
        refine=_REFINE,
    )
