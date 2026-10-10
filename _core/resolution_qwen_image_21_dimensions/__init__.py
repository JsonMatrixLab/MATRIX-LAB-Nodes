"""Qwen Image 2.1 native resolution table and ComfyUI utility node."""

from __future__ import annotations


ASPECT_RATIOS = ("1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16")
NATIVE_SIZES = {
    "1:1": (2048, 2048),
    "4:3": (2400, 1792),
    "3:4": (1792, 2400),
    "3:2": (2528, 1696),
    "2:3": (1696, 2528),
    "16:9": (2752, 1536),
    "9:16": (1536, 2752),
}
GRID = 32
MAX_LONGEST_SIDE = 2752
MAX_AREA = 2400 * 1792


class QwenImage21ResolutionError(ValueError):
    """The requested Qwen Image 2.1 geometry is invalid or unsupported."""


def validate_qwen_image_21_dimensions(width, height):
    """Validate and return width and height."""
    if type(width) is not int or type(height) is not int:
        raise QwenImage21ResolutionError("width and height must be integers")
    if width <= 0 or height <= 0 or width % GRID or height % GRID:
        raise QwenImage21ResolutionError("width and height must be positive multiples of 32")
    longest_dimension = max(width, height)
    if longest_dimension > MAX_LONGEST_SIDE:
        raise QwenImage21ResolutionError(
            f"longest dimension must be at most {MAX_LONGEST_SIDE}"
        )
    if width * height > MAX_AREA:
        raise QwenImage21ResolutionError(f"pixel area must be at most {MAX_AREA}")
    return width, height


def calculate_qwen_image_21_resolution(*, aspect_ratio):
    """Return only the exact native size selected from the pinned model-card table."""
    if type(aspect_ratio) is not str or aspect_ratio not in NATIVE_SIZES:
        raise QwenImage21ResolutionError(
            f"aspect_ratio must be one of {ASPECT_RATIOS}"
        )
    return validate_qwen_image_21_dimensions(*NATIVE_SIZES[aspect_ratio])


def execute_utility_operation(item):
    """Execute the compiler's exact Qwen Image 2.1 resolution payload."""
    if not isinstance(item, dict) or set(item) != {"aspect_ratio"}:
        raise QwenImage21ResolutionError(
            "a Qwen Image 2.1 resolution payload needs exactly aspect_ratio"
        )
    return calculate_qwen_image_21_resolution(**item)


class MATRIX_QwenImage21Resolution:
    """Geometry-only utility for the seven Qwen Image 2.1 native sizes."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "aspect_ratio": (list(ASPECT_RATIOS), {"default": "1:1"}),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    OUTPUT_IS_LIST = (False, False)
    FUNCTION = "calculate"
    CATEGORY = "MATRIX LAB/Resolution & Layout"

    def calculate(self, aspect_ratio):
        return calculate_qwen_image_21_resolution(aspect_ratio=aspect_ratio)


__all__ = [
    "ASPECT_RATIOS",
    "GRID",
    "MAX_AREA",
    "MAX_LONGEST_SIDE",
    "MATRIX_QwenImage21Resolution",
    "NATIVE_SIZES",
    "QwenImage21ResolutionError",
    "calculate_qwen_image_21_resolution",
    "execute_utility_operation",
    "validate_qwen_image_21_dimensions",
]
