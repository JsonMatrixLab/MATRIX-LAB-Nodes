"""Deterministic, batch-safe camera and color grading for ComfyUI IMAGE tensors."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import math

import numpy as np
from PIL import Image, ImageFilter
import torch
import torch.nn.functional as torch_functional


__all__ = [
    "CameraLookError",
    "CameraLookProcessingError",
    "CameraLookValidationError",
    "camera_look",
    "execute_utility_operation",
]


class CameraLookError(RuntimeError):
    """Base error for the camera-look operation."""


class CameraLookValidationError(CameraLookError, ValueError):
    """The tensor or a runtime widget value violates the operation contract."""


class CameraLookProcessingError(CameraLookError):
    """An image-processing dependency returned an invalid result."""


@dataclass(frozen=True)
class _Parameters:
    chromatic_aberration: float
    demosaic_pixel_blur: bool
    noise_strength: float
    kernel_motion_blur: int
    jpeg_compression: int
    seed: int


def _check_interrupted() -> None:
    """Use ComfyUI's engine check when the block is loaded inside ComfyUI."""
    try:
        from comfy.model_management import throw_exception_if_processing_interrupted
    except ImportError:
        return
    throw_exception_if_processing_interrupted()


def _require_bool(name: str, value: object) -> bool:
    if type(value) is not bool:
        raise CameraLookValidationError(f"{name} must be an exact boolean")
    return value


def _require_float(name: str, value: object, minimum: float, maximum: float) -> float:
    if type(value) not in (float, int) or isinstance(value, bool):
        raise CameraLookValidationError(f"{name} must be a finite real number")
    converted = float(value)
    if not math.isfinite(converted) or not minimum <= converted <= maximum:
        raise CameraLookValidationError(f"{name} must be in [{minimum}, {maximum}]")
    return converted


def _require_int(name: str, value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise CameraLookValidationError(f"{name} must be an exact integer in [{minimum}, {maximum}]")
    return value


def _validate_image(image: object, *, check_samples: bool = True) -> torch.Tensor:
    if not isinstance(image, torch.Tensor):
        raise CameraLookValidationError("image must be a torch tensor")
    if image.ndim != 4:
        raise CameraLookValidationError("image must have rank 4 in [B,H,W,C] order")
    _, height, width, channels = image.shape
    if height < 1 or width < 1:
        raise CameraLookValidationError("image spatial dimensions must both be positive")
    if channels not in (3, 4):
        raise CameraLookValidationError("image channel count must be exactly 3 or 4")
    if not image.is_floating_point():
        raise CameraLookValidationError("image must use a floating dtype")
    # Float8 does not implement isfinite on all pinned torch builds. Empty and
    # disabled paths deliberately avoid even this conversion/allocation.
    if check_samples and image.numel() and not bool(
        torch.isfinite(image.to(dtype=torch.float32)).all().item()
    ):
        raise CameraLookValidationError("image contains a non-finite sample")
    return image


def _derive_frame_seed(seed: int, frame_index: int) -> int:
    """SplitMix64 gives each frame a stable stream without global RNG state."""
    mask = (1 << 64) - 1
    value = (seed + frame_index + 0x9E3779B97F4A7C15) & mask
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
    return (value ^ (value >> 31)) & mask


def _apply_noise(rgb: torch.Tensor, strength: float, seed: int) -> torch.Tensor:
    if strength == 0.0:
        return rgb
    generator = torch.Generator(device="cpu")
    generator.manual_seed(seed)
    amount = (strength / 5.0) ** 2
    samples = rgb.to(torch.float32)
    photons = samples * (80.0 / 255.0)
    shot = (torch.poisson(photons, generator=generator) - photons) * (2.0 * amount)
    read = torch.randn(samples.shape, generator=generator, dtype=torch.float32) * (4.0 * amount)
    return (samples + shot + read).round().clamp_(0, 255).to(torch.uint8)


def _apply_demosaic(rgb: torch.Tensor) -> torch.Tensor:
    image = Image.fromarray(rgb.numpy(), mode="RGB")
    filtered = image.filter(ImageFilter.GaussianBlur(radius=0.5))
    return torch.from_numpy(np.asarray(filtered, dtype=np.uint8).copy())


def _apply_aberration(rgb: torch.Tensor, amount: float) -> torch.Tensor:
    shift = round(amount * rgb.shape[1] / 500.0)
    if shift == 0:
        return rgb
    shifted = rgb.clone()
    shifted[:, :, 0] = 0
    shifted[:, :, 2] = 0
    if shift < rgb.shape[1]:
        shifted[:, shift:, 0] = rgb[:, :-shift, 0]
        shifted[:, :-shift, 2] = rgb[:, shift:, 2]
    return shifted


def _apply_motion_blur(rgb: torch.Tensor, requested_kernel: int) -> torch.Tensor:
    if requested_kernel == 1:
        return rgb
    kernel_size = requested_kernel if requested_kernel % 2 else requested_kernel + 1
    kernel = torch.full((1, 1, kernel_size), 1.0 / kernel_size, dtype=torch.float32)
    result = torch.empty_like(rgb)
    padding = kernel_size // 2
    for row_index in range(rgb.shape[0]):
        _check_interrupted()
        row = rgb[row_index].to(torch.float32).transpose(0, 1).unsqueeze(1)
        blurred = torch_functional.conv1d(row, kernel, padding=padding)
        result[row_index] = blurred.squeeze(1).transpose(0, 1).round().clamp_(0, 255).to(torch.uint8)
    return result


def _jpeg_round_trip(rgb: torch.Tensor, quality: int) -> torch.Tensor:
    height, width, _ = rgb.shape
    buffer = BytesIO()
    try:
        Image.fromarray(rgb.numpy(), mode="RGB").save(buffer, format="JPEG", quality=quality)
        buffer.seek(0)
        with Image.open(buffer) as decoded:
            if decoded.mode != "RGB" or decoded.size != (width, height):
                raise CameraLookProcessingError(
                    f"JPEG decoder returned mode={decoded.mode!r}, size={decoded.size!r}"
                )
            decoded.load()
            array = np.asarray(decoded, dtype=np.uint8).copy()
    except CameraLookProcessingError:
        raise
    except Exception as error:
        raise CameraLookProcessingError("JPEG round trip failed") from error
    if array.shape != (height, width, 3):
        raise CameraLookProcessingError(f"JPEG decoder returned malformed shape {array.shape!r}")
    return torch.from_numpy(array)


def _process_frame(frame: torch.Tensor, parameters: _Parameters, frame_index: int) -> torch.Tensor:
    _check_interrupted()
    frame_float = frame.to(dtype=torch.float32)
    alpha = frame_float[..., 3].clone() if frame_float.shape[-1] == 4 else None
    rgb = (frame_float[..., :3].clamp(0, 1) * 255.0).round().to(torch.uint8)

    rgb = _apply_noise(rgb, parameters.noise_strength, _derive_frame_seed(parameters.seed, frame_index))
    _check_interrupted()
    if parameters.demosaic_pixel_blur:
        rgb = _apply_demosaic(rgb)
    _check_interrupted()
    rgb = _apply_aberration(rgb, parameters.chromatic_aberration)
    _check_interrupted()
    rgb = _apply_motion_blur(rgb, parameters.kernel_motion_blur)
    _check_interrupted()
    rgb = _jpeg_round_trip(rgb, parameters.jpeg_compression)
    _check_interrupted()

    output_rgb = rgb.to(torch.float32).div_(255.0)
    if alpha is None:
        return output_rgb.contiguous()
    return torch.cat((output_rgb, alpha.unsqueeze(-1)), dim=-1).contiguous()


def camera_look(
    image: torch.Tensor,
    *,
    enabled: bool,
    chromatic_aberration: float,
    demosaic_pixel_blur: bool,
    noise_strength: float,
    kernel_motion_blur: int,
    jpeg_compression: int,
    look_seed: int,
) -> torch.Tensor:
    """Apply the contracted camera look to every BHWC frame in order."""
    enabled = _require_bool("enabled", enabled)
    demosaic_pixel_blur = _require_bool("demosaic_pixel_blur", demosaic_pixel_blur)
    parameters = _Parameters(
        chromatic_aberration=_require_float("chromatic_aberration", chromatic_aberration, 0.0, 10.0),
        demosaic_pixel_blur=demosaic_pixel_blur,
        noise_strength=_require_float("noise_strength", noise_strength, 0.0, 5.0),
        kernel_motion_blur=_require_int("kernel_motion_blur", kernel_motion_blur, 1, 51),
        jpeg_compression=_require_int("jpeg_compression", jpeg_compression, 85, 100),
        seed=_require_int("look_seed", look_seed, 0, (1 << 64) - 1),
    )
    image = _validate_image(image, check_samples=enabled)
    if not enabled or image.shape[0] == 0:
        return image

    output = torch.empty(image.shape, dtype=torch.float32, device=image.device)
    for frame_index in range(image.shape[0]):
        _check_interrupted()
        frame = image[frame_index].detach().to(device="cpu", dtype=torch.float32)
        processed = _process_frame(frame, parameters, frame_index)
        output[frame_index].copy_(processed)
    return output.contiguous()


def execute_utility_operation(item):
    """Factory seam: execute the named camera-look contract without positional migration."""
    if not isinstance(item, dict) or "image" not in item:
        raise CameraLookValidationError("color.camera-look requires an input mapping with 'image'")
    return (
        camera_look(
            item["image"],
            enabled=item.get("enabled", True),
            chromatic_aberration=item.get("chromatic_aberration", 0.0),
            demosaic_pixel_blur=item.get("demosaic_pixel_blur", True),
            noise_strength=item.get("noise_strength", 0.0),
            kernel_motion_blur=item.get("kernel_motion_blur", 1),
            jpeg_compression=item.get("jpeg_compression", 98),
            # Deprecated 0.6.x dict-path alias; generated widgets use look_seed.
            look_seed=item.get("look_seed", item.get("seed", 0)),
        ),
    )
