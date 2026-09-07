"""sample.crop-tail-paste: crop-local masked latent refinement and exact-window paste."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import torch
import torch.nn.functional as F

from ..sample_latent_tail import (
    CORE_SAMPLER_NAMES,
    SCHEDULER_NAMES,
)

__all__ = [
    "CORE_SAMPLER_NAMES",
    "SCHEDULER_NAMES",
    "CropGeometry",
    "CropTailError",
    "CropTailValidationError",
    "color_match_crop",
    "compute_crop_geometry",
    "configure_factory_crop_tail",
    "crop_tail_paste",
    "execute_utility_operation",
    "grow_feather_mask",
]

_LOG = logging.getLogger("MATRIX.CropTailPaste")
_FLOAT_DTYPES = frozenset({torch.float16, torch.bfloat16, torch.float32, torch.float64})
_DECODE_EXCURSION_MIN = -0.02
_DECODE_EXCURSION_MAX = 1.02


class CropTailError(RuntimeError):
    """Base class for crop-tail-paste failures."""


class CropTailValidationError(CropTailError, ValueError):
    """An input violates the block contract."""


@dataclass(frozen=True)
class CropGeometry:
    """Inclusive-mask crop converted to exclusive source window and resize target."""

    x0: int
    y0: int
    x1: int
    y1: int
    target_width: int
    target_height: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0


def _ceil16(value: int) -> int:
    return ((value + 15) // 16) * 16


def _integer(name: str, value: Any, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise CropTailValidationError(f"{name} must be an integer within {low}..{high}")
    return value


def _number(name: str, value: Any, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CropTailValidationError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise CropTailValidationError(f"{name} must be finite and within {low}..{high}")
    return result


def compute_crop_geometry(
    hard_mask: torch.Tensor, *, guide_size: int, padding_px: int
) -> CropGeometry | None:
    """Resolve one hard `[H,W]` mask into its shifted, 16-aligned crop and target."""
    guide = _integer("guide_size", guide_size, 256, 2048)
    if guide % 16:
        raise CropTailValidationError("guide_size must be divisible by 16")
    padding = _integer("padding_px", padding_px, 0, 512)
    if not isinstance(hard_mask, torch.Tensor) or hard_mask.ndim != 2:
        raise CropTailValidationError("hard_mask must be a tensor of shape [H,W]")
    height, width = hard_mask.shape
    if height < 1 or width < 1:
        raise CropTailValidationError("hard_mask must contain pixels")
    points = torch.nonzero(hard_mask == 1, as_tuple=False)
    if points.numel() == 0:
        return None

    ymin, xmin = points.amin(dim=0).tolist()
    ymax, xmax = points.amax(dim=0).tolist()
    if xmax - xmin + 1 + 2 * padding < 16 or ymax - ymin + 1 + 2 * padding < 16:
        return None
    center_x = (xmin + xmax) / 2.0
    center_y = (ymin + ymax) / 2.0
    box_width = min(max(xmax - xmin + 1, 256), guide, width)
    box_height = min(max(ymax - ymin + 1, 256), guide, height)
    pad_x = min(max((width - box_width) // 2, 0), padding)
    pad_y = min(max((height - box_height) // 2, 0), padding)
    crop_width = min(_ceil16(min(box_width + 2 * pad_x, width)), width)
    crop_height = min(_ceil16(min(box_height + 2 * pad_y, height)), height)
    x0 = max(0, min(int(center_x - crop_width / 2), width - crop_width))
    y0 = max(0, min(int(center_y - crop_height / 2), height - crop_height))

    ratio = crop_width / crop_height
    if ratio > 1:
        target_width = guide
        target_height = int(guide / ratio)
    else:
        target_height = guide
        target_width = int(guide * ratio)
    target_width = max(16, _ceil16(target_width))
    target_height = max(16, _ceil16(target_height))
    return CropGeometry(
        x0=x0,
        y0=y0,
        x1=x0 + crop_width,
        y1=y0 + crop_height,
        target_width=target_width,
        target_height=target_height,
    )


def _resize_image(image: torch.Tensor, height: int, width: int) -> torch.Tensor:
    dtype = image.dtype
    nchw = image.permute(0, 3, 1, 2).to(torch.float32)
    resized = F.interpolate(nchw, size=(height, width), mode="bicubic", align_corners=False, antialias=True)
    return resized.permute(0, 2, 3, 1).to(dtype=dtype)


def _resize_mask(mask: torch.Tensor, height: int, width: int) -> torch.Tensor:
    resized = F.interpolate(
        mask.unsqueeze(1).to(torch.float32), size=(height, width), mode="bilinear", align_corners=False
    )
    return resized[:, 0]


def _cross_dilate(mask: torch.Tensor) -> torch.Tensor:
    padded = F.pad(mask.unsqueeze(1), (1, 1, 1, 1), mode="constant", value=0)
    values = (
        padded[:, :, 1:-1, 1:-1],
        padded[:, :, :-2, 1:-1],
        padded[:, :, 2:, 1:-1],
        padded[:, :, 1:-1, :-2],
        padded[:, :, 1:-1, 2:],
    )
    return torch.stack(values, dim=0).amax(dim=0)[:, 0]


def grow_feather_mask(mask: torch.Tensor, feather_px: int) -> torch.Tensor:
    """Cross-dilate by six, fill binary holes, then apply a reflect-padded Gaussian."""
    radius = _integer("feather_px", feather_px, 0, 64)
    if not isinstance(mask, torch.Tensor) or mask.ndim != 3:
        raise CropTailValidationError("mask must be a tensor of shape [B,H,W]")
    grown = mask.to(torch.float32)
    for _ in range(6):
        grown = _cross_dilate(grown)

    import scipy.ndimage

    filled_items = [
        torch.from_numpy(scipy.ndimage.binary_fill_holes(item.detach().cpu().numpy() > 0))
        for item in grown
    ]
    filled = torch.stack(filled_items).to(device=mask.device, dtype=torch.float32)
    if radius == 0:
        return filled
    if filled.shape[-2] <= radius or filled.shape[-1] <= radius:
        raise CropTailValidationError("feather_px must be smaller than both crop dimensions")
    coords = torch.arange(-radius, radius + 1, device=mask.device, dtype=torch.float32)
    kernel = torch.exp(-(coords * coords) / (2.0 * radius * radius))
    kernel = kernel / kernel.sum()
    work = F.pad(filled.unsqueeze(1), (radius, radius, 0, 0), mode="reflect")
    work = F.conv2d(work, kernel.view(1, 1, 1, -1))
    work = F.pad(work, (0, 0, radius, radius), mode="reflect")
    return F.conv2d(work, kernel.view(1, 1, -1, 1))[:, 0]


def color_match_crop(decoded: torch.Tensor, source: torch.Tensor) -> torch.Tensor:
    """Match per-channel population mean/std over one crop without touching the source."""
    if decoded.shape != source.shape or decoded.ndim != 4 or decoded.shape[-1] != 3:
        raise CropTailValidationError("colour-match tensors must have equal [B,H,W,3] geometry")
    calc = decoded.to(torch.float32)
    reference = source.to(torch.float32)
    dims = (1, 2)
    mean_in = calc.mean(dim=dims, keepdim=True)
    mean_ref = reference.mean(dim=dims, keepdim=True)
    std_in = calc.std(dim=dims, keepdim=True, unbiased=False)
    std_ref = reference.std(dim=dims, keepdim=True, unbiased=False)
    matched = (calc - mean_in) * (std_ref / std_in.clamp_min(1e-6)) + mean_ref
    return matched.clamp(0.0, 1.0).to(decoded.dtype)


def _validate_inputs(image: Any, mask: Any) -> tuple[int, int, int]:
    if not isinstance(image, torch.Tensor) or image.ndim != 4:
        raise CropTailValidationError("image must be an IMAGE tensor of shape [B,H,W,C]")
    if image.dtype not in _FLOAT_DTYPES or image.shape[0] < 1 or image.shape[1] < 1 or image.shape[2] < 1:
        raise CropTailValidationError("image must be a nonempty floating-point tensor")
    if image.shape[-1] not in (3, 4):
        raise CropTailValidationError("image must have RGB or RGBA channels")
    if not bool(torch.isfinite(image).all()) or bool((image < 0).any()) or bool((image > 1).any()):
        raise CropTailValidationError("image values must be finite and within [0,1]")
    if not isinstance(mask, torch.Tensor) or mask.ndim != 3 or mask.dtype not in _FLOAT_DTYPES:
        raise CropTailValidationError("mask must be a floating MASK tensor of shape [B,H,W]")
    if tuple(mask.shape[-2:]) != tuple(image.shape[1:3]) or mask.shape[0] not in (1, image.shape[0]):
        raise CropTailValidationError("mask geometry must match image and batch must be 1 or image batch")
    if not bool(torch.isfinite(mask).all()) or bool((mask < 0).any()) or bool((mask > 1).any()):
        raise CropTailValidationError("mask values must be finite and within [0,1]")
    return image.shape[0], image.shape[1], image.shape[2]


def crop_tail_paste(
    *,
    image: torch.Tensor,
    mask: torch.Tensor,
    model: Any,
    noise: Any,
    positive: Any,
    vae: Any,
    guide_size: int = 1024,
    padding_px: int = 64,
    start_sigma: float = 0.22,
    steps: int = 3,
    sampler_name: str = "euler_ancestral",
    scheduler: str = "beta57",
    feather_px: int = 12,
    color_match: bool = False,
    encode: Callable[[Any, torch.Tensor], Mapping[str, Any]],
    decode: Callable[[Any, Mapping[str, Any]], torch.Tensor],
    run_tail: Callable[..., Mapping[str, Any]],
) -> torch.Tensor:
    """Refine each masked crop through injected VAE/tail seams and paste it independently."""
    batch, _, _ = _validate_inputs(image, mask)
    guide = _integer("guide_size", guide_size, 256, 2048)
    if guide % 16:
        raise CropTailValidationError("guide_size must be divisible by 16")
    padding = _integer("padding_px", padding_px, 0, 512)
    sigma = _number("start_sigma", start_sigma, 0.05, 0.60)
    count = _integer("steps", steps, 1, 12)
    feather = _integer("feather_px", feather_px, 0, 64)
    if sampler_name not in CORE_SAMPLER_NAMES:
        raise CropTailValidationError(f"unknown sampler_name {sampler_name!r}")
    if scheduler not in SCHEDULER_NAMES:
        raise CropTailValidationError(f"unknown scheduler {scheduler!r}")
    if not isinstance(color_match, bool):
        raise CropTailValidationError("color_match must be boolean")
    if any(value is None for value in (model, noise, positive, vae)):
        raise CropTailValidationError("model, noise, positive and vae are required")
    if not all(callable(seam) for seam in (encode, decode, run_tail)):
        raise CropTailValidationError("encode, decode and run_tail must be callable")

    hard = torch.round(mask)
    geometries = [
        compute_crop_geometry(
            hard[0 if mask.shape[0] == 1 else index],
            guide_size=guide,
            padding_px=padding,
        )
        for index in range(batch)
    ]
    if all(geometry is None for geometry in geometries):
        _LOG.info("crop tail skipped: empty mask")
        return image
    output = image.clone()
    for index in range(batch):
        mask_index = 0 if mask.shape[0] == 1 else index
        geometry = geometries[index]
        if geometry is None:
            _LOG.info("crop tail skipped: empty mask")
            continue
        source = image[index : index + 1, geometry.y0 : geometry.y1, geometry.x0 : geometry.x1, :3]
        source_large = _resize_image(source, geometry.target_height, geometry.target_width)
        hard_crop = hard[mask_index : mask_index + 1, geometry.y0 : geometry.y1, geometry.x0 : geometry.x1]
        mask_large = _resize_mask(hard_crop, geometry.target_height, geometry.target_width)
        blend_large = grow_feather_mask(mask_large, feather)
        latent = encode(vae, source_large)
        if not isinstance(latent, Mapping) or "samples" not in latent:
            raise CropTailError("encode seam must return a LATENT mapping with 'samples'")
        refined = run_tail(
            model,
            noise,
            positive,
            dict(latent),
            blend_large,
            sigma,
            count,
            sampler_name,
            scheduler,
        )
        if not isinstance(refined, Mapping) or "samples" not in refined:
            raise CropTailError("run_tail seam must return a LATENT mapping with 'samples'")
        decoded = decode(vae, dict(refined))
        if not isinstance(decoded, torch.Tensor) or decoded.shape != source_large.shape:
            raise CropTailError("decode seam must return pixels with the encoded crop geometry")
        decoded = decoded.to(device=image.device, dtype=image.dtype)
        if not bool(torch.isfinite(decoded).all()):
            raise CropTailError("decode seam returned non-finite pixels")
        decoded_min = float(decoded.amin().item())
        decoded_max = float(decoded.amax().item())
        if decoded_min < _DECODE_EXCURSION_MIN or decoded_max > _DECODE_EXCURSION_MAX:
            raise CropTailError(
                "decode seam returned pixels outside the tolerated "
                f"[{_DECODE_EXCURSION_MIN},{_DECODE_EXCURSION_MAX}] excursion: "
                f"{decoded_min}..{decoded_max}"
            )
        if decoded_min < 0.0 or decoded_max > 1.0:
            _LOG.warning(
                "clamped finite VAE decode excursion: range %.6f..%.6f",
                decoded_min,
                decoded_max,
            )
        # ComfyUI VAEs can produce small finite pixel excursions outside [0,1].
        # Clamp the generated crop at the image boundary before resizing and
        # again after blending so the node always honours its IMAGE contract.
        decoded = decoded.clamp(0.0, 1.0)
        if color_match:
            decoded = color_match_crop(decoded, source_large)
        patch = _resize_image(decoded, geometry.height, geometry.width).clamp(0.0, 1.0)[0]
        alpha = _resize_mask(blend_large, geometry.height, geometry.width)[0].to(image.dtype).unsqueeze(-1)
        destination = output[index, geometry.y0 : geometry.y1, geometry.x0 : geometry.x1, :3]
        output[index, geometry.y0 : geometry.y1, geometry.x0 : geometry.x1, :3] = (
            destination * (1.0 - alpha) + patch * alpha
        )
    return output.clamp_(0.0, 1.0)


_ENCODE: Callable[[Any, torch.Tensor], Mapping[str, Any]] | None = None
_DECODE: Callable[[Any, Mapping[str, Any]], torch.Tensor] | None = None
_RUN_TAIL: Callable[..., Mapping[str, Any]] | None = None


def configure_factory_crop_tail(
    encode: Callable[[Any, torch.Tensor], Mapping[str, Any]],
    decode: Callable[[Any, Mapping[str, Any]], torch.Tensor],
    run_tail: Callable[..., Mapping[str, Any]],
) -> None:
    """Install VAE encode/decode and latent-tail runtime adapters."""
    if not all(callable(seam) for seam in (encode, decode, run_tail)):
        raise TypeError("factory crop-tail adapters must be callable")
    global _ENCODE, _DECODE, _RUN_TAIL
    _ENCODE, _DECODE, _RUN_TAIL = encode, decode, run_tail


def execute_utility_operation(item: dict) -> tuple[torch.Tensor]:
    """Factory seam for the compiled MATRIX_CropTailPaste node."""
    if not isinstance(item, dict):
        raise CropTailValidationError("sample.crop-tail-paste requires an input mapping")
    required = ("image", "mask", "model", "noise", "positive", "vae")
    missing = [name for name in required if name not in item]
    if missing:
        raise CropTailValidationError("missing crop-tail input(s): " + ", ".join(missing))
    if _ENCODE is None or _DECODE is None or _RUN_TAIL is None:
        raise CropTailValidationError("sample.crop-tail-paste runtime adapters are not configured")
    result = crop_tail_paste(
        image=item["image"],
        mask=item["mask"],
        model=item["model"],
        noise=item["noise"],
        positive=item["positive"],
        vae=item["vae"],
        guide_size=item.get("guide_size", 1024),
        padding_px=item.get("padding_px", 64),
        start_sigma=item.get("start_sigma", 0.22),
        steps=item.get("steps", 3),
        sampler_name=item.get("sampler_name", "euler_ancestral"),
        scheduler=item.get("scheduler", "beta57"),
        feather_px=item.get("feather_px", 12),
        color_match=item.get("color_match", False),
        encode=_ENCODE,
        decode=_DECODE,
        run_tail=_RUN_TAIL,
    )
    return (result,)
