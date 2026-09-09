"""Deterministic, mask-aware photographic finishing for ComfyUI IMAGE tensors."""

from __future__ import annotations

from dataclasses import dataclass
import math

import torch
import torch.nn.functional as F


@dataclass(frozen=True, slots=True)
class _Profile:
    contrast: float
    warmth: float
    saturation: float
    detail: float
    luma_texture: float
    chroma_texture: float
    luma_sigma: float
    chroma_sigma: float
    highlight_threshold: float


# Display-referred starting points. These are creative profiles, not measured camera/ISO claims.
PROFILES = {
    "Clean Digital": _Profile(0.025, 0.000, 1.00, 0.12, 0.0020, 0.0006, 0.35, 1.20, 0.94),
    "Everyday Capture": _Profile(0.045, 0.012, 0.98, 0.08, 0.0045, 0.0015, 0.45, 1.50, 0.88),
    "Low Light": _Profile(-0.010, 0.018, 0.94, -0.04, 0.0080, 0.0040, 0.70, 2.20, 0.72),
}

# The coordinate field consumes exactly 32 seed bits; do not expose colliding higher values.
_MAX_SEED = (1 << 32) - 1
_CORE_TILE = 512
_MAX_HALO = 8


class PhotoFinisherValidationError(ValueError):
    """The caller violated the image.photo-finisher contract."""


class PhotoFinisherAllocationError(RuntimeError):
    """A bounded validation or work tile could not be allocated."""


def _supported_dtypes() -> tuple[torch.dtype, ...]:
    return (torch.float16, torch.float32, torch.bfloat16)


def _require_real(name: str, value: object, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhotoFinisherValidationError(f"{name} must be a finite real number in {minimum}..{maximum}")
    converted = float(value)
    if not math.isfinite(converted) or not minimum <= converted <= maximum:
        raise PhotoFinisherValidationError(f"{name} must be a finite real number in {minimum}..{maximum}")
    return converted


def _validate_controls(profile, mix, texture, detail, contrast, warmth, saturation, seed):
    if type(profile) is not str or profile not in PROFILES:
        raise PhotoFinisherValidationError(f"profile must be one of {tuple(PROFILES)}")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= _MAX_SEED:
        raise PhotoFinisherValidationError(f"seed must be an integer in 0..{_MAX_SEED}")
    return (
        PROFILES[profile],
        _require_real("mix", mix, 0.0, 1.0),
        _require_real("texture", texture, 0.0, 2.0),
        _require_real("detail", detail, -1.0, 1.0),
        _require_real("contrast", contrast, -1.0, 1.0),
        _require_real("warmth", warmth, -1.0, 1.0),
        _require_real("saturation", saturation, 0.0, 2.0),
    )


def _validate_structure(image: object, mask: object) -> tuple[torch.Tensor, torch.Tensor | None]:
    if not isinstance(image, torch.Tensor) or image.ndim != 4:
        raise PhotoFinisherValidationError("IMAGE must be a Torch tensor in BHWC layout")
    if any(size < 1 for size in image.shape) or image.shape[-1] not in (3, 4):
        raise PhotoFinisherValidationError("IMAGE must be non-empty BHWC RGB or RGBA")
    if image.dtype not in _supported_dtypes():
        raise PhotoFinisherValidationError("IMAGE dtype must be fp16, fp32, or bf16")
    if mask is None:
        return image, None
    if not isinstance(mask, torch.Tensor) or mask.ndim != 3:
        raise PhotoFinisherValidationError("MASK must be a Torch tensor in BHW layout")
    if not mask.is_floating_point():
        raise PhotoFinisherValidationError("MASK must use a floating dtype")
    if tuple(mask.shape[1:]) != tuple(image.shape[1:3]):
        raise PhotoFinisherValidationError("MASK height and width must exactly match IMAGE")
    if mask.shape[0] not in (1, image.shape[0]):
        raise PhotoFinisherValidationError("MASK batch must be 1 or equal the IMAGE batch")
    return image, mask


def _check_interruption() -> None:
    try:
        from comfy.model_management import throw_exception_if_processing_interrupted
    except ImportError:
        return
    throw_exception_if_processing_interrupted()


def _tile_bounds(height: int, width: int, halo: int):
    for y0 in range(0, height, _CORE_TILE):
        y1 = min(y0 + _CORE_TILE, height)
        for x0 in range(0, width, _CORE_TILE):
            x1 = min(x0 + _CORE_TILE, width)
            yield (
                y0, y1, x0, x1,
                max(0, y0 - halo), min(height, y1 + halo),
                max(0, x0 - halo), min(width, x1 + halo),
            )


def _validate_values(image: torch.Tensor, mask: torch.Tensor | None) -> None:
    try:
        height, width = image.shape[1:3]
        for frame in range(image.shape[0]):
            for y0, y1, x0, x1, *_ in _tile_bounds(height, width, 0):
                _check_interruption()
                tile = image[frame, y0:y1, x0:x1].float()
                if not bool(torch.isfinite(tile).all()) or bool((tile < 0).any()) or bool((tile > 1).any()):
                    raise PhotoFinisherValidationError("IMAGE values must be finite and in [0, 1]")
        if mask is not None:
            for frame in range(mask.shape[0]):
                for y0, y1, x0, x1, *_ in _tile_bounds(height, width, 0):
                    _check_interruption()
                    tile = mask[frame, y0:y1, x0:x1].float()
                    if not bool(torch.isfinite(tile).all()) or bool((tile < 0).any()) or bool((tile > 1).any()):
                        raise PhotoFinisherValidationError("MASK values must be finite and in [0, 1]")
    except PhotoFinisherValidationError:
        raise
    except (torch.cuda.OutOfMemoryError, MemoryError) as error:
        raise PhotoFinisherAllocationError("image.photo-finisher could not allocate a bounded validation tile") from error
    except RuntimeError as error:
        message = str(error).lower()
        if ("out of memory" in message or "can't allocate memory" in message
                or "cannot allocate memory" in message or "defaultcpuallocator" in message
                or "not enough memory" in message):
            raise PhotoFinisherAllocationError("image.photo-finisher could not allocate a bounded validation tile") from error
        raise PhotoFinisherValidationError(f"IMAGE or MASK values could not be validated: {error}") from error


def _coordinate_noise(height, width, *, channels, device, y0, x0, frame, seed, stream):
    """A stateless uniform field keyed by pixel coordinate, frame, stream, and uint64 seed."""
    mask32 = 0xFFFFFFFF
    y = torch.arange(y0, y0 + height, dtype=torch.int64, device=device).reshape(height, 1, 1)
    x = torch.arange(x0, x0 + width, dtype=torch.int64, device=device).reshape(1, width, 1)
    channel = torch.arange(channels, dtype=torch.int64, device=device).reshape(1, 1, channels)
    salt = ((seed & mask32) ^ (((seed >> 32) * 0x9E3779B1) & mask32)
            ^ ((frame * 0x85EBCA77) & mask32) ^ ((stream * 0xC2B2AE3D) & mask32))
    hashed = ((x * 0x27D4EB2F) ^ (y * 0x165667B1) ^ (channel * 0x7FEB352D) ^ salt) & mask32
    hashed = hashed ^ (hashed >> 16)
    hashed = (hashed * 0x45D9F3B) & mask32
    hashed = hashed ^ (hashed >> 16)
    hashed = (hashed * 0x45D9F3B) & mask32
    hashed = hashed ^ (hashed >> 16)
    return hashed.to(torch.float32).mul_(2.0 / 4294967296.0).sub_(1.0)


def _gaussian_blur(field: torch.Tensor, sigma: float) -> torch.Tensor:
    if sigma <= 0:
        return field
    radius = min(math.ceil(3.0 * sigma), _MAX_HALO)
    positions = torch.arange(-radius, radius + 1, dtype=torch.float32, device=field.device)
    kernel = torch.exp(-positions.square() / (2.0 * sigma * sigma))
    kernel = kernel / kernel.sum()
    channels = field.shape[-1]
    nchw = field.permute(2, 0, 1).unsqueeze(0)
    horizontal = kernel.reshape(1, 1, 1, -1).expand(channels, 1, 1, -1)
    vertical = kernel.reshape(1, 1, -1, 1).expand(channels, 1, -1, 1)
    nchw = F.conv2d(F.pad(nchw, (radius, radius, 0, 0), mode="replicate"), horizontal, groups=channels)
    nchw = F.conv2d(F.pad(nchw, (0, 0, radius, radius), mode="replicate"), vertical, groups=channels)
    return nchw.squeeze(0).permute(1, 2, 0)


def _tone_and_color(rgb, profile, *, contrast, warmth, saturation):
    contrast_scale = 1.0 + profile.contrast + contrast * 0.25
    toned = (rgb - 0.5) * contrast_scale + 0.5
    luminance = toned[..., 0:1] * 0.2126 + toned[..., 1:2] * 0.7152 + toned[..., 2:3] * 0.0722
    warmth_amount = profile.warmth + warmth * 0.04
    midtone = (4.0 * luminance * (1.0 - luminance)).clamp(0.0, 1.0)
    bias = toned.new_tensor((1.0, 0.20, -1.0)).reshape(1, 1, 3)
    toned = (toned + bias * warmth_amount * midtone).clamp(0.0, 1.0)
    # Saturation owns the final chroma amplitude, including a true grayscale endpoint.
    luminance = toned[..., 0:1] * 0.2126 + toned[..., 1:2] * 0.7152 + toned[..., 2:3] * 0.0722
    saturation_scale = profile.saturation * saturation
    return (luminance + (toned - luminance) * saturation_scale).clamp(0.0, 1.0)


def _finish_rgb(rgb, profile, *, texture, detail, contrast, warmth, saturation,
                frame, seed, y0, x0):
    toned = _tone_and_color(rgb, profile, contrast=contrast, warmth=warmth, saturation=saturation)
    detail_amount = profile.detail + detail * 0.35
    if detail_amount:
        toned = (toned + (toned - _gaussian_blur(toned, 0.8)) * detail_amount).clamp(0.0, 1.0)
    if texture:
        luma = _coordinate_noise(rgb.shape[0], rgb.shape[1], channels=1, device=rgb.device,
                                 y0=y0, x0=x0, frame=frame, seed=seed, stream=0)
        chroma = _coordinate_noise(rgb.shape[0], rgb.shape[1], channels=3, device=rgb.device,
                                   y0=y0, x0=x0, frame=frame, seed=seed, stream=1)
        luma = _gaussian_blur(luma, profile.luma_sigma) * (profile.luma_texture * texture)
        chroma = _gaussian_blur(chroma, profile.chroma_sigma) * (profile.chroma_texture * texture * saturation)
        luminance = toned[..., 0:1] * 0.2126 + toned[..., 1:2] * 0.7152 + toned[..., 2:3] * 0.0722
        fade = ((1.0 - luminance) / (1.0 - profile.highlight_threshold)).clamp(0.0, 1.0)
        toned = (toned + (luma.expand(-1, -1, 3) + chroma) * fade).clamp(0.0, 1.0)
    return toned


def photo_finish(image: torch.Tensor, mask: torch.Tensor | None = None, *,
                 profile: str = "Everyday Capture", mix: float = 1.0,
                 texture: float = 1.0, detail: float = 1.0, contrast: float = 0.0,
                 warmth: float = 0.0, saturation: float = 1.0, seed: int = 42) -> torch.Tensor:
    """Finish a display-referred BHWC image without resizing or encoding it."""
    image, mask = _validate_structure(image, mask)
    profile_values, mix, texture, detail, contrast, warmth, saturation = _validate_controls(
        profile, mix, texture, detail, contrast, warmth, saturation, seed
    )
    _validate_values(image, mask)
    if mix == 0.0 or (mask is not None and not bool(torch.count_nonzero(mask))):
        return image

    halo = max(math.ceil(3.0 * 0.8), math.ceil(3.0 * profile_values.luma_sigma),
               math.ceil(3.0 * profile_values.chroma_sigma))
    halo = min(halo, _MAX_HALO)
    try:
        result = torch.empty_like(image)
        batch, height, width, _ = image.shape
        for frame in range(batch):
            _check_interruption()
            mask_frame = None if mask is None else mask[0 if mask.shape[0] == 1 else frame]
            for y0, y1, x0, x1, ey0, ey1, ex0, ex1 in _tile_bounds(height, width, halo):
                _check_interruption()
                expanded = image[frame, ey0:ey1, ex0:ex1, :3].float()
                finished = _finish_rgb(
                    expanded, profile_values, texture=texture, detail=detail,
                    contrast=contrast, warmth=warmth, saturation=saturation,
                    frame=frame, seed=seed, y0=ey0, x0=ex0,
                )
                ly0, ly1, lx0, lx1 = y0 - ey0, y1 - ey0, x0 - ex0, x1 - ex0
                source = image[frame, y0:y1, x0:x1, :3]
                source_float = source.float()
                weight = mix
                if mask_frame is not None:
                    mask_tile = mask_frame[y0:y1, x0:x1].to(device=image.device, dtype=torch.float32)
                    weight = mask_tile.unsqueeze(-1) * mix
                blended = torch.lerp(source_float, finished[ly0:ly1, lx0:lx1], weight).clamp(0, 1)
                converted = blended.to(image.dtype)
                if mask_frame is not None:
                    converted = torch.where((mask_tile == 0).unsqueeze(-1), source, converted)
                result[frame, y0:y1, x0:x1, :3] = converted
                if image.shape[-1] == 4:
                    result[frame, y0:y1, x0:x1, 3] = image[frame, y0:y1, x0:x1, 3]
    except (PhotoFinisherValidationError, InterruptedError):
        raise
    except (torch.cuda.OutOfMemoryError, MemoryError) as error:
        raise PhotoFinisherAllocationError("image.photo-finisher could not allocate a bounded work tile; no partial output returned") from error
    except RuntimeError as error:
        message = str(error).lower()
        if ("out of memory" in message or "can't allocate memory" in message
                or "cannot allocate memory" in message or "defaultcpuallocator" in message
                or "not enough memory" in message):
            raise PhotoFinisherAllocationError("image.photo-finisher could not allocate a bounded work tile; no partial output returned") from error
        raise
    return result


def execute_utility_operation(item):
    if not isinstance(item, dict) or "image" not in item:
        raise PhotoFinisherValidationError("image.photo-finisher requires an input mapping with 'image'")
    allowed = {"image", "mask", "profile", "mix", "texture", "detail", "contrast", "warmth", "saturation", "seed"}
    if set(item) - allowed:
        raise PhotoFinisherValidationError("image.photo-finisher received unsupported input fields")
    return (photo_finish(
        item["image"], item.get("mask"), profile=item.get("profile", "Everyday Capture"),
        mix=item.get("mix", 1.0), texture=item.get("texture", 1.0),
        detail=item.get("detail", 1.0), contrast=item.get("contrast", 0.0),
        warmth=item.get("warmth", 0.0), saturation=item.get("saturation", 1.0),
        seed=item.get("seed", 42),
    ),)


__all__ = [
    "PROFILES", "PhotoFinisherAllocationError", "PhotoFinisherValidationError",
    "execute_utility_operation", "photo_finish",
]
