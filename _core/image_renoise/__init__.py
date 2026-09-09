"""Deterministic, bounded-memory sensor grain for ComfyUI IMAGE tensors."""

from __future__ import annotations

import math

import torch
import torch.nn.functional as F


ISO_PRESETS = {
    "ISO 0 (Off)": (0.000, 0.000, 0.00, 0.0, 0.00),
    "ISO 50": (0.004, 0.002, 0.35, 1.2, 0.98),
    "ISO 100 (Clean)": (0.008, 0.005, 0.40, 1.5, 0.95),
    "ISO 200": (0.012, 0.008, 0.45, 1.8, 0.90),
    "ISO 400": (0.018, 0.012, 0.50, 2.0, 0.85),
    "ISO 800": (0.025, 0.016, 0.55, 2.5, 0.78),
    "ISO 1600": (0.035, 0.025, 0.65, 3.0, 0.70),
    "Night Mode": (0.025, 0.035, 1.20, 4.0, 0.50),
}

_MAX_SEED = 18446744073709551615
_CORE_TILE = 1024
_MAX_HALO = 12


class RenoiseValidationError(ValueError):
    """The caller violated the image.renoise public contract."""


class RenoiseAllocationError(RuntimeError):
    """A bounded work tile could not be allocated."""


def _supported_dtypes() -> tuple[torch.dtype, ...]:
    dtypes = [torch.float32, torch.bfloat16]
    for name in (
        "float8_e4m3fn",
        "float8_e4m3fnuz",
        "float8_e5m2",
        "float8_e5m2fnuz",
    ):
        dtype = getattr(torch, name, None)
        if dtype is not None:
            dtypes.append(dtype)
    return tuple(dtypes)


def _validate_structure(image: torch.Tensor) -> None:
    if not isinstance(image, torch.Tensor):
        raise RenoiseValidationError("IMAGE must be a Torch tensor in BHWC layout")
    if image.ndim != 4:
        raise RenoiseValidationError("IMAGE must have rank 4 in BHWC layout")
    if any(size < 1 for size in image.shape):
        raise RenoiseValidationError("IMAGE batch, height, width, and channel dimensions must be non-empty")
    if image.shape[-1] not in (3, 4):
        raise RenoiseValidationError("IMAGE channel dimension must be exactly RGB or RGBA")
    if image.dtype not in _supported_dtypes():
        raise RenoiseValidationError(
            f"IMAGE dtype {image.dtype} on device {image.device} is unsupported; expected fp32, bf16, or fp8"
        )


def _validate_seed(grain_seed: int) -> None:
    if (
        isinstance(grain_seed, bool)
        or not isinstance(grain_seed, int)
        or not 0 <= grain_seed <= _MAX_SEED
    ):
        raise RenoiseValidationError(
            f"grain_seed must be an integer in the inclusive range 0..{_MAX_SEED}"
        )


def _validate_strength(strength: float) -> float:
    if isinstance(strength, bool) or not isinstance(strength, (int, float)):
        raise RenoiseValidationError("strength must be a finite real number in the inclusive range 0.0..2.0")
    value = float(strength)
    if not math.isfinite(value) or not 0.0 <= value <= 2.0:
        raise RenoiseValidationError("strength must be a finite real number in the inclusive range 0.0..2.0")
    return value


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
            ey0 = max(0, y0 - halo)
            ey1 = min(height, y1 + halo)
            ex0 = max(0, x0 - halo)
            ex1 = min(width, x1 + halo)
            yield y0, y1, x0, x1, ey0, ey1, ex0, ex1


def _validate_values(image: torch.Tensor) -> None:
    height, width = image.shape[1:3]
    try:
        for frame in range(image.shape[0]):
            for y0, y1, x0, x1, *_ in _tile_bounds(height, width, 0):
                _check_interruption()
                tile = image[frame, y0:y1, x0:x1].float()
                if not bool(torch.isfinite(tile).all()):
                    raise RenoiseValidationError("IMAGE values must all be finite")
                if bool((tile < 0.0).any()) or bool((tile > 1.0).any()):
                    raise RenoiseValidationError("IMAGE values must be in the inclusive range [0, 1]")
    except RenoiseValidationError:
        raise
    except torch.cuda.OutOfMemoryError as error:
        raise RenoiseAllocationError(
            f"image.renoise could not allocate a bounded validation tile on {image.device}; no partial output returned"
        ) from error
    except RuntimeError as error:
        if "out of memory" in str(error).lower():
            raise RenoiseAllocationError(
                f"image.renoise could not allocate a bounded validation tile on {image.device}; no partial output returned"
            ) from error
        raise RenoiseValidationError(
            f"IMAGE dtype {image.dtype} cannot be validated on device {image.device}: {error}"
        ) from error


def _coordinate_noise(
    height: int,
    width: int,
    *,
    channels: int,
    device: torch.device,
    y0: int,
    x0: int,
    frame: int,
    seed: int,
    stream: int,
    offset: torch.Tensor,
) -> torch.Tensor:
    """Generate a stateless local random field, stable across work-tile boundaries.

    Integer hash (lowbias32-style avalanche) over (x, y, channel, frame, stream, seed): exact on every
    backend, zero-mean uniform in [-1, 1). The earlier float32 ``frac(sin(...))`` hash aliased at
    image coordinates above about 1000 px (regular stripes with a period of about seven rows and a
    negative mean), which the pod evidence of 2026-09-03 exposed at 1536x2048.
    """
    mask32 = 0xFFFFFFFF
    y = torch.arange(y0, y0 + height, dtype=torch.int64, device=device).reshape(height, 1, 1)
    x = torch.arange(x0, x0 + width, dtype=torch.int64, device=device).reshape(1, width, 1)
    channel = torch.arange(channels, dtype=torch.int64, device=device).reshape(1, 1, channels)
    seed_low = seed & mask32
    seed_high = (seed >> 32) & mask32
    offset_bits = int(float(offset.item()) * 4294967296.0) & mask32
    salt = (
        (int(frame) * 0x27D4EB2F)
        ^ (int(stream) * 0x165667B1)
        ^ seed_low
        ^ ((seed_high * 0x9E3779B1) & mask32)
        ^ offset_bits
    ) & mask32
    h = ((x * 0x9E3779B1) ^ (y * 0x85EBCA77) ^ (channel * 0xC2B2AE3D) ^ salt) & mask32
    h = h ^ (h >> 16)
    h = (h * 0x7FEB352D) & mask32
    h = h ^ (h >> 15)
    h = (h * 0x846CA68B) & mask32
    h = h ^ (h >> 16)
    return h.to(torch.float32).mul_(1.0 / 4294967296.0).mul_(2.0).sub_(1.0)


def _gaussian_blur(field: torch.Tensor, sigma: float) -> torch.Tensor:
    if sigma <= 0.0:
        return field
    radius = min(int(math.ceil(3.0 * sigma)), _MAX_HALO)
    positions = torch.arange(-radius, radius + 1, dtype=torch.float32, device=field.device)
    kernel = torch.exp(-(positions.square()) / (2.0 * sigma * sigma))
    kernel = kernel / kernel.sum()
    channels = field.shape[-1]
    nchw = field.permute(2, 0, 1).unsqueeze(0)
    horizontal = kernel.reshape(1, 1, 1, -1).expand(channels, 1, 1, -1)
    vertical = kernel.reshape(1, 1, -1, 1).expand(channels, 1, -1, 1)
    nchw = F.conv2d(F.pad(nchw, (radius, radius, 0, 0), mode="replicate"), horizontal, groups=channels)
    nchw = F.conv2d(F.pad(nchw, (0, 0, radius, radius), mode="replicate"), vertical, groups=channels)
    return nchw.squeeze(0).permute(1, 2, 0)


def _highlight_mask(rgb: torch.Tensor, threshold: float) -> torch.Tensor:
    luminance = rgb[..., 0:1] * 0.2126 + rgb[..., 1:2] * 0.7152 + rgb[..., 2:3] * 0.0722
    fade = ((1.0 - luminance) / (1.0 - threshold)).clamp(0.0, 1.0)
    return torch.where(luminance <= threshold, torch.ones_like(fade), fade)


def _renoise(
    image: torch.Tensor,
    seed: int,
    coefficients: tuple[float, float, float, float, float],
    strength: float,
) -> torch.Tensor:
    luma_amplitude, chroma_amplitude, luma_sigma, chroma_sigma, threshold = coefficients
    luma_amplitude *= strength
    chroma_amplitude *= strength
    halo = min(max(math.ceil(3.0 * luma_sigma), math.ceil(3.0 * chroma_sigma)), _MAX_HALO)
    batch, height, width, _ = image.shape
    result = torch.empty_like(image)
    generator = torch.Generator(device=image.device)
    generator.manual_seed(seed)
    stream_offsets = torch.rand(2, dtype=torch.float32, device=image.device, generator=generator)
    for frame in range(batch):
        _check_interruption()
        for y0, y1, x0, x1, ey0, ey1, ex0, ex1 in _tile_bounds(height, width, halo):
            _check_interruption()
            expanded_height = ey1 - ey0
            expanded_width = ex1 - ex0
            luma = _coordinate_noise(
                expanded_height,
                expanded_width,
                channels=1,
                device=image.device,
                y0=ey0,
                x0=ex0,
                frame=frame,
                seed=seed,
                stream=0,
                offset=stream_offsets[0],
            )
            luma = _gaussian_blur(luma, luma_sigma).mul_(luma_amplitude)
            _check_interruption()
            chroma = _coordinate_noise(
                expanded_height,
                expanded_width,
                channels=3,
                device=image.device,
                y0=ey0,
                x0=ex0,
                frame=frame,
                seed=seed,
                stream=1,
                offset=stream_offsets[1],
            )
            chroma = _gaussian_blur(chroma, chroma_sigma).mul_(chroma_amplitude)
            _check_interruption()
            local_y0, local_y1 = y0 - ey0, y1 - ey0
            local_x0, local_x1 = x0 - ex0, x1 - ex0
            noise = luma[local_y0:local_y1, local_x0:local_x1].expand(-1, -1, 3)
            noise = noise + chroma[local_y0:local_y1, local_x0:local_x1]
            rgb = image[frame, y0:y1, x0:x1, :3].float()
            mask = _highlight_mask(rgb, threshold)
            processed = (rgb + noise * mask).clamp_(0.0, 1.0).to(image.dtype)
            result[frame, y0:y1, x0:x1, :3] = processed
            if image.shape[-1] == 4:
                result[frame, y0:y1, x0:x1, 3] = image[frame, y0:y1, x0:x1, 3]
    return result


def renoise_image(
    image: torch.Tensor,
    grain_seed: int = 0,
    iso_preset: str = "ISO 400",
    strength: float = 1.0,
) -> torch.Tensor:
    """Apply the selected deterministic sensor-grain preset to a BHWC IMAGE tensor."""
    _validate_structure(image)
    _validate_seed(grain_seed)
    strength = _validate_strength(strength)
    if iso_preset not in ISO_PRESETS:
        raise RenoiseValidationError(
            f"iso_preset must be one of {tuple(ISO_PRESETS)}; received {iso_preset!r}"
        )
    _validate_values(image)
    if iso_preset == "ISO 0 (Off)" or strength == 0.0:
        return image
    try:
        return _renoise(image, grain_seed, ISO_PRESETS[iso_preset], strength)
    except (RenoiseValidationError, InterruptedError):
        raise
    except torch.cuda.OutOfMemoryError as error:
        raise RenoiseAllocationError(
            f"image.renoise could not allocate a bounded work tile on {image.device}; no partial output returned"
        ) from error
    except RuntimeError as error:
        if "out of memory" in str(error).lower():
            raise RenoiseAllocationError(
                f"image.renoise could not allocate a bounded work tile on {image.device}; no partial output returned"
            ) from error
        raise


def execute_utility_operation(item):
    """Factory seam: one declared input mapping to one IMAGE output."""
    if not isinstance(item, dict) or "image" not in item:
        raise RenoiseValidationError("image.renoise requires an input mapping with 'image'")
    return (
        renoise_image(
            item["image"],
            # Deprecated 0.6.x dict-path alias; generated widgets use grain_seed.
            grain_seed=item.get("grain_seed", item.get("seed", 0)),
            iso_preset=item.get("iso_preset", "ISO 400"),
            strength=item.get("strength", 1.0),
        ),
    )


__all__ = [
    "ISO_PRESETS",
    "RenoiseAllocationError",
    "RenoiseValidationError",
    "execute_utility_operation",
    "renoise_image",
]
