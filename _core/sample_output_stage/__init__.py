"""sample.output-stage: factor-driven exact-size final image processing."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import torch
import torch.nn.functional as F

from ..sample_latent_tail import CORE_SAMPLER_NAMES, SCHEDULER_NAMES, TailSchedule

__all__ = [
    "CORE_SAMPLER_NAMES", "SCHEDULER_NAMES", "OutputStageError", "OutputStageSigmas",
    "OutputStageValidationError", "configure_factory_output_stage",
    "compute_sigma_ceiling", "execute_utility_operation", "output_stage",
]

_FLOAT_DTYPES = frozenset({torch.float16, torch.bfloat16, torch.float32, torch.float64})
_RESIZE_METHODS = frozenset({"lanczos", "bicubic", "area"})


class OutputStageError(RuntimeError):
    """Base class for output-stage failures."""


class OutputStageValidationError(OutputStageError, ValueError):
    """An input violates the output-stage contract."""


@dataclass(frozen=True)
class OutputStageSigmas:
    """Request resolved by the injected sample.latent-tail runtime seam."""

    ceiling: float
    steps: int
    scheduler: str


def _integer(name: str, value: Any, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise OutputStageValidationError(f"{name} must be an integer within {low}..{high}")
    return value


def _number(name: str, value: Any, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OutputStageValidationError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise OutputStageValidationError(f"{name} must be finite and within {low}..{high}")
    return result


def compute_sigma_ceiling(factor: float, sigma_base: float, sigma_per_octave: float) -> float:
    """Resolve and clamp the output-tail ceiling for a positive scale factor."""
    scale = _number("factor", factor, float.fromhex("0x1.0p-1022"), float.fromhex("0x1.fffffffffffffp+1023"))
    base = _number("sigma_base", sigma_base, 0.05, 0.40)
    per_octave = _number("sigma_per_octave", sigma_per_octave, 0.0, 0.30)
    return min(max(base + per_octave * math.log2(scale), 0.05), 0.40)


def _lanczos_weights(source: int, target: int, device: torch.device):
    scale = source / target
    filter_scale = max(scale, 1.0)
    radius = 3.0 * filter_scale
    taps = max(1, int(math.ceil(radius * 2)))
    centres = (torch.arange(target, device=device, dtype=torch.float64) + 0.5) * scale - 0.5
    starts = torch.floor(centres - radius + 1.0).to(torch.int64)
    offsets = torch.arange(taps, device=device, dtype=torch.int64)
    raw = starts[:, None] + offsets[None, :]
    distance = centres[:, None] - raw.to(torch.float64)
    weights = torch.sinc(distance / filter_scale) * torch.sinc(distance / radius)
    weights = torch.where(distance.abs() < radius, weights, torch.zeros_like(weights))
    weights = weights / weights.sum(dim=1, keepdim=True).clamp_min(torch.finfo(weights.dtype).eps)
    return raw.clamp(0, source - 1), weights.to(torch.float32)


def _resize_lanczos(image: torch.Tensor, height: int, width: int) -> torch.Tensor:
    work = image.to(torch.float32)
    y_index, y_weight = _lanczos_weights(image.shape[1], height, image.device)
    work = (work[:, y_index, :, :] * y_weight[None, :, :, None, None]).sum(dim=2)
    x_index, x_weight = _lanczos_weights(image.shape[2], width, image.device)
    work = (work[:, :, x_index, :] * x_weight[None, None, :, :, None]).sum(dim=3)
    # Lanczos ringing overshoots by a few thousandths at hard edges; the IMAGE contract is [0, 1].
    return work.clamp(0.0, 1.0).to(image.dtype)


def _resize(image: torch.Tensor, height: int, width: int, method: str) -> torch.Tensor:
    if tuple(image.shape[1:3]) == (height, width):
        return image.clone()
    if method == "lanczos":
        return _resize_lanczos(image, height, width)
    nchw = image.permute(0, 3, 1, 2).to(torch.float32)
    if method == "bicubic":
        result = F.interpolate(nchw, size=(height, width), mode="bicubic", align_corners=False, antialias=True)
    else:
        result = F.interpolate(nchw, size=(height, width), mode="area")
    return result.permute(0, 2, 3, 1).clamp(0.0, 1.0).to(image.dtype)


def _validate_image(image: Any) -> tuple[int, int]:
    if not isinstance(image, torch.Tensor) or image.ndim != 4:
        raise OutputStageValidationError("image must be an IMAGE tensor of shape [B,H,W,C]")
    if image.dtype not in _FLOAT_DTYPES or image.shape[0] < 1 or image.shape[-1] != 3:
        raise OutputStageValidationError("image must be a nonempty floating RGB tensor")
    if image.shape[1] < 1 or image.shape[2] < 1 or not bool(torch.isfinite(image).all()):
        raise OutputStageValidationError("image must have nonempty geometry and finite values")
    return int(image.shape[1]), int(image.shape[2])


def output_stage(
    *, image: torch.Tensor, model: Any, noise: Any, positive: Any, vae: Any,
    target_width: int, target_height: int, upscale_model: Any = None,
    sigma_base: float = 0.15, sigma_per_octave: float = 0.10, steps: int = 3,
    sampler_name: str = "res_multistep", scheduler: str = "beta57",
    resize_method: str = "lanczos", decode_tile: int = 512, decode_overlap: int = 64,
    encode: Callable[..., Mapping[str, Any]], decode_tiled: Callable[..., torch.Tensor],
    tail: Callable[..., tuple[Mapping[str, Any], TailSchedule]],
    upscale_with_model: Callable[..., torch.Tensor],
) -> tuple[torch.Tensor, str]:
    """Apply the factor-driven output policy through injected ComfyUI seams."""
    source_height, source_width = _validate_image(image)
    width = _integer("target_width", target_width, 16, 8192)
    height = _integer("target_height", target_height, 16, 8192)
    if width % 16 or height % 16:
        raise OutputStageValidationError("target_width and target_height must be multiples of 16")
    if source_width * height != source_height * width:
        raise OutputStageValidationError(
            f"target aspect ratio {width}x{height} must match image {source_width}x{source_height}"
        )
    base = _number("sigma_base", sigma_base, 0.05, 0.40)
    per_octave = _number("sigma_per_octave", sigma_per_octave, 0.0, 0.30)
    count = _integer("steps", steps, 1, 12)
    tile = _integer("decode_tile", decode_tile, 64, 2048)
    overlap = _integer("decode_overlap", decode_overlap, 0, 512)
    if overlap >= tile:
        raise OutputStageValidationError("decode_overlap must be smaller than decode_tile")
    if sampler_name not in CORE_SAMPLER_NAMES:
        raise OutputStageValidationError(f"unknown sampler_name {sampler_name!r}")
    if scheduler not in SCHEDULER_NAMES:
        raise OutputStageValidationError(f"unknown scheduler {scheduler!r}")
    if resize_method not in _RESIZE_METHODS:
        raise OutputStageValidationError(f"unknown resize_method {resize_method!r}")
    if any(value is None for value in (model, noise, positive, vae)):
        raise OutputStageValidationError("model, noise, positive and vae are required")
    if not all(callable(seam) for seam in (encode, decode_tiled, tail, upscale_with_model)):
        raise OutputStageValidationError("encode, decode_tiled, tail and upscale_with_model must be callable")

    factor = max(width, height) / max(source_width, source_height)
    if factor < 1.0:
        result = _resize(image, height, width, resize_method)
        return result, f"factor={factor:.3f} downscale method={resize_method} ceiling=none sigmas=none"
    if (width, height) == (source_width, source_height):
        return image.clone(), f"factor={factor:.3f} pass ceiling=none sigmas=none"

    work = image
    if upscale_model is not None:
        work = upscale_with_model(upscale_model, work)
        if not isinstance(work, torch.Tensor) or work.ndim != 4 or work.shape[0] != image.shape[0] or work.shape[-1] != 3:
            raise OutputStageError("upscale_with_model seam must return an RGB IMAGE with the input batch")
        if not bool(torch.isfinite(work).all()):
            raise OutputStageError("upscale_with_model seam returned non-finite pixels")
        work = work.clamp(0.0, 1.0)  # ESRGAN-family models overshoot slightly
    work = _resize(work.to(device=image.device, dtype=image.dtype), height, width, resize_method)
    latent = encode(vae, work)
    if not isinstance(latent, Mapping) or "samples" not in latent:
        raise OutputStageError("VAE encode seam must return a LATENT mapping with 'samples'")
    ceiling = compute_sigma_ceiling(factor, base, per_octave)
    tailed = tail(
        model, noise, positive, dict(latent),
        OutputStageSigmas(ceiling=ceiling, steps=count, scheduler=scheduler), sampler_name,
    )
    if not isinstance(tailed, tuple) or len(tailed) != 2:
        raise OutputStageError("tail seam must return (LATENT, TailSchedule)")
    refined, schedule = tailed
    if not isinstance(refined, Mapping) or "samples" not in refined or not isinstance(schedule, TailSchedule):
        raise OutputStageError("tail seam must return a LATENT mapping and TailSchedule")
    decoded = decode_tiled(vae, dict(refined), tile, overlap)
    if not isinstance(decoded, torch.Tensor) or tuple(decoded.shape) != (image.shape[0], height, width, 3):
        observed = tuple(decoded.shape) if isinstance(decoded, torch.Tensor) else type(decoded).__name__
        raise OutputStageError(
            f"tiled decode must return exact target geometry {(image.shape[0], height, width, 3)}; got {observed}"
        )
    if not bool(torch.isfinite(decoded).all()):
        raise OutputStageError("tiled decode returned non-finite pixels")
    result = decoded.to(device=image.device, dtype=image.dtype).clamp(0.0, 1.0)
    sigma_text = ", ".join(f"{value:.3f}" for value in schedule.sigmas)
    info = f"factor={factor:.3f} ceiling={ceiling:.3f} sigmas=[{sigma_text}]"
    return result, info


_ENCODE: Callable[..., Mapping[str, Any]] | None = None
_DECODE_TILED: Callable[..., torch.Tensor] | None = None
_TAIL: Callable[..., tuple[Mapping[str, Any], TailSchedule]] | None = None
_UPSCALE: Callable[..., torch.Tensor] | None = None


def configure_factory_output_stage(vae_encode, vae_decode_tiled, tail, upscale_with_model) -> None:
    """Install VAE, latent-tail and optional Core upscaler runtime adapters."""
    if not all(callable(seam) for seam in (vae_encode, vae_decode_tiled, tail, upscale_with_model)):
        raise TypeError("factory output-stage adapters must be callable")
    global _ENCODE, _DECODE_TILED, _TAIL, _UPSCALE
    _ENCODE, _DECODE_TILED, _TAIL, _UPSCALE = vae_encode, vae_decode_tiled, tail, upscale_with_model


def execute_utility_operation(item: dict) -> tuple[torch.Tensor, str]:
    """Factory seam for the compiled MATRIX_OutputStage node."""
    if not isinstance(item, dict):
        raise OutputStageValidationError("sample.output-stage requires an input mapping")
    required = ("image", "model", "noise", "positive", "vae", "target_width", "target_height")
    missing = [name for name in required if name not in item]
    if missing:
        raise OutputStageValidationError("missing output-stage input(s): " + ", ".join(missing))
    if any(seam is None for seam in (_ENCODE, _DECODE_TILED, _TAIL, _UPSCALE)):
        raise OutputStageValidationError("sample.output-stage runtime adapters are not configured")
    return output_stage(
        image=item["image"], model=item["model"], noise=item["noise"], positive=item["positive"],
        vae=item["vae"], target_width=item["target_width"], target_height=item["target_height"],
        upscale_model=item.get("upscale_model"), sigma_base=item.get("sigma_base", 0.15),
        sigma_per_octave=item.get("sigma_per_octave", 0.10), steps=item.get("steps", 3),
        sampler_name=item.get("sampler_name", "res_multistep"), scheduler=item.get("scheduler", "beta57"),
        resize_method=item.get("resize_method", "lanczos"), decode_tile=item.get("decode_tile", 512),
        decode_overlap=item.get("decode_overlap", 64), encode=_ENCODE, decode_tiled=_DECODE_TILED,
        tail=_TAIL, upscale_with_model=_UPSCALE,
    )
