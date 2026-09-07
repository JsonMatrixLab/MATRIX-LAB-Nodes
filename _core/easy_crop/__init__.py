"""Pure backend capability for the MATRIXLAB Easy Crop node."""

from __future__ import annotations

import hashlib
import math
import warnings
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path


ASPECT_CHOICES = ("Free", "1:1", "16:9", "9:16", "Custom")
MAX_IMAGE_PIXELS = 100_000_000
MIN_CUSTOM_RATIO = 1
MAX_CUSTOM_RATIO = 1000


class EasyCropValidationError(ValueError):
    """Fail-closed refusal for malformed state or an unsafe image."""

    code = "MATRIX_EASY_CROP_VALIDATION"


def _folder_paths():
    try:
        import folder_paths
    except ImportError as exc:  # pragma: no cover - supplied by ComfyUI
        raise EasyCropValidationError("MATRIXLAB Easy Crop requires ComfyUI.") from exc
    return folder_paths


def resolve_image_path(image: str, folder_paths_module=None) -> Path:
    """Resolve one ComfyUI annotated upload string to an existing regular file."""

    if not isinstance(image, str) or not image or "\x00" in image:
        raise EasyCropValidationError("Invalid image upload string.")
    paths = folder_paths_module or _folder_paths()
    try:
        if not paths.exists_annotated_filepath(image):
            raise EasyCropValidationError(f"Invalid image file: {image}")
        resolved = Path(paths.get_annotated_filepath(image)).resolve(strict=True)
    except EasyCropValidationError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise EasyCropValidationError(f"Invalid image file: {image}") from exc
    if not resolved.is_file():
        raise EasyCropValidationError(f"Invalid image file: {image}")
    return resolved


def validate_image_path(image: str, folder_paths_module=None):
    """Return the ComfyUI VALIDATE_INPUTS result for an upload string."""

    try:
        resolve_image_path(image, folder_paths_module)
    except EasyCropValidationError as exc:
        return str(exc)
    return True


def image_digest(image: str, folder_paths_module=None) -> str:
    """Return the SHA-256 hex digest used by a generated adapter's IS_CHANGED hook."""

    path = resolve_image_path(image, folder_paths_module)
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise EasyCropValidationError(f"Image file could not be read: {image}") from exc
    return digest.hexdigest()


def _validate_contract(
    aspect_ratio,
    custom_ratio_width,
    custom_ratio_height,
    crop_x,
    crop_y,
    crop_width,
    crop_height,
):
    if aspect_ratio not in ASPECT_CHOICES:
        raise EasyCropValidationError(f"Unsupported aspect choice: {aspect_ratio!r}")
    for name, value in (
        ("custom_ratio_width", custom_ratio_width),
        ("custom_ratio_height", custom_ratio_height),
    ):
        if type(value) is not int or not MIN_CUSTOM_RATIO <= value <= MAX_CUSTOM_RATIO:
            raise EasyCropValidationError(
                f"{name} must be an integer in the inclusive range "
                f"{MIN_CUSTOM_RATIO}..{MAX_CUSTOM_RATIO}"
            )
    coordinates = {
        "crop_x": crop_x,
        "crop_y": crop_y,
        "crop_width": crop_width,
        "crop_height": crop_height,
    }
    for name, value in coordinates.items():
        if type(value) not in (int, float) or not math.isfinite(value):
            raise EasyCropValidationError(f"{name} must be a finite number")
    if not 0.0 <= crop_x < 1.0 or not 0.0 <= crop_y < 1.0:
        raise EasyCropValidationError("Crop origin must be normalized within the image.")
    if not 0.0 < crop_width <= 1.0 or not 0.0 < crop_height <= 1.0:
        raise EasyCropValidationError("Crop dimensions must be normalized and positive.")
    if (
        Decimal(str(crop_x)) + Decimal(str(crop_width)) > 1
        or Decimal(str(crop_y)) + Decimal(str(crop_height)) > 1
    ):
        raise EasyCropValidationError("Crop rectangle extends outside the image.")


def _pixel_box(width, height, crop_x, crop_y, crop_width, crop_height):
    def scaled(value, dimension, rounding):
        return int((value * dimension).to_integral_value(rounding=rounding))

    x = Decimal(str(crop_x))
    y = Decimal(str(crop_y))
    crop_w = Decimal(str(crop_width))
    crop_h = Decimal(str(crop_height))
    left = scaled(x, width, ROUND_FLOOR)
    top = scaled(y, height, ROUND_FLOOR)
    pixel_width = max(1, scaled(crop_w, width, ROUND_HALF_UP))
    pixel_height = max(1, scaled(crop_h, height, ROUND_HALF_UP))
    right = min(width, left + pixel_width)
    bottom = min(height, top + pixel_height)
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise EasyCropValidationError("Crop rectangle resolves outside the image bounds.")
    return left, top, right, bottom


def crop_image(
    image,
    aspect_ratio,
    custom_ratio_width,
    custom_ratio_height,
    crop_x,
    crop_y,
    crop_width,
    crop_height,
):
    """Decode, EXIF-orient, validate, and crop one static image into IMAGE and MASK tensors."""

    _validate_contract(
        aspect_ratio,
        custom_ratio_width,
        custom_ratio_height,
        crop_x,
        crop_y,
        crop_width,
        crop_height,
    )
    path = resolve_image_path(image)
    try:
        import numpy as np
        import torch
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - runtime dependency failure
        raise EasyCropValidationError(
            "MATRIXLAB Easy Crop requires NumPy, Pillow, and Torch."
        ) from exc

    bomb_warning = getattr(Image, "DecompressionBombWarning", None)
    try:
        with warnings.catch_warnings():
            if bomb_warning is not None:
                warnings.simplefilter("error", bomb_warning)
            with Image.open(path) as source:
                if getattr(source, "is_animated", False) or getattr(source, "n_frames", 1) != 1:
                    raise EasyCropValidationError("Animated images are not supported.")
                source_width, source_height = source.size
                if (
                    type(source_width) is not int
                    or type(source_height) is not int
                    or source_width <= 0
                    or source_height <= 0
                    or source_width * source_height > MAX_IMAGE_PIXELS
                ):
                    raise EasyCropValidationError("Image exceeds the 100 megapixel limit.")
                oriented = ImageOps.exif_transpose(source)
                width, height = oriented.size
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    raise EasyCropValidationError("Image exceeds the 100 megapixel limit.")
                box = _pixel_box(
                    width, height, crop_x, crop_y, crop_width, crop_height
                )
                cropped = oriented.crop(box)
                if "transparency" in cropped.info:
                    cropped = cropped.convert("RGBA")
                rgb = np.asarray(cropped.convert("RGB"), dtype=np.float32) / 255.0
                if "A" in cropped.getbands():
                    alpha = np.asarray(cropped.getchannel("A"), dtype=np.float32) / 255.0
                    mask = 1.0 - alpha
                else:
                    mask = np.zeros((cropped.height, cropped.width), dtype=np.float32)
    except EasyCropValidationError:
        raise
    except Exception as exc:
        raise EasyCropValidationError("Image could not be decoded safely.") from exc

    if rgb.shape != (cropped.height, cropped.width, 3) or mask.shape != (
        cropped.height,
        cropped.width,
    ):
        raise EasyCropValidationError("Decoded crop has an invalid tensor shape.")
    return (torch.from_numpy(rgb.copy()).unsqueeze(0), torch.from_numpy(mask.copy()).unsqueeze(0))


def execute_utility_operation(item):
    """Execute one compiler-provided Easy Crop payload."""

    required = {
        "image",
        "aspect_ratio",
        "custom_ratio_width",
        "custom_ratio_height",
        "crop_x",
        "crop_y",
        "crop_width",
        "crop_height",
    }
    if not isinstance(item, dict) or set(item) != required:
        raise EasyCropValidationError(
            "Easy Crop inputs must contain exactly: " + ", ".join(sorted(required))
        )
    return crop_image(**item)


def validate_image_input(image):
    """Return the generated adapter's ComfyUI VALIDATE_INPUTS result."""

    return validate_image_path(image)


def input_digest(image):
    """Return the generated adapter's ComfyUI IS_CHANGED digest."""

    return image_digest(image)


__all__ = [
    "ASPECT_CHOICES",
    "EasyCropValidationError",
    "MAX_IMAGE_PIXELS",
    "crop_image",
    "execute_utility_operation",
    "image_digest",
    "input_digest",
    "resolve_image_path",
    "validate_image_path",
    "validate_image_input",
]
