"""MATRIX H3 resolution geometry with exact generation pixel outputs."""

from __future__ import annotations


ASPECT_RATIOS = ("1:1", "16:9", "9:16", "4:3", "3:4", "Custom")
RESOLUTION_TIERS = ("1K", "2K")
CUSTOM_MIN = 32
CUSTOM_MAX = 2048

_PRESET_OUTPUTS = {
    ("1:1", "1K"): (1024, 1024),
    ("16:9", "1K"): (1024, 576),
    ("9:16", "1K"): (576, 1024),
    ("4:3", "1K"): (1024, 768),
    ("3:4", "1K"): (768, 1024),
    ("1:1", "2K"): (2048, 2048),
    ("16:9", "2K"): (2048, 1152),
    ("9:16", "2K"): (1152, 2048),
    ("4:3", "2K"): (2048, 1536),
    ("3:4", "2K"): (1536, 2048),
}


class H3ResolutionError(ValueError):
    """The requested H3 geometry is invalid or unsupported."""


def _require_choice(value, *, name, choices):
    if type(value) is not str or value not in choices:
        raise H3ResolutionError(f"{name} must be one of {choices}")


def _require_custom_dimension(value, *, name):
    if type(value) is not int:
        raise H3ResolutionError(f"{name} must be an integer")
    if not CUSTOM_MIN <= value <= CUSTOM_MAX:
        raise H3ResolutionError(f"{name} must be between {CUSTOM_MIN} and {CUSTOM_MAX}")
    if value % 32:
        raise H3ResolutionError(f"{name} must be a multiple of 32")
    return value


def calculate_h3_resolution(*, aspect_ratio, resolution_tier, custom_width, custom_height):
    """Return the exact generation width and height selected by the user."""
    _require_choice(aspect_ratio, name="aspect_ratio", choices=ASPECT_RATIOS)
    _require_choice(resolution_tier, name="resolution_tier", choices=RESOLUTION_TIERS)
    custom_width = _require_custom_dimension(custom_width, name="custom_width")
    custom_height = _require_custom_dimension(custom_height, name="custom_height")
    if aspect_ratio == "Custom":
        return custom_width, custom_height
    return _PRESET_OUTPUTS[(aspect_ratio, resolution_tier)]


class MATRIX_H3Resolution:
    """Geometry-only H3 utility; it does not infer models or transform images."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "aspect_ratio": (list(ASPECT_RATIOS), {"default": "9:16"}),
                "resolution_tier": (list(RESOLUTION_TIERS), {"default": "1K"}),
                "custom_width": (
                    "INT",
                    {"default": 576, "min": CUSTOM_MIN, "max": CUSTOM_MAX, "step": 32},
                ),
                "custom_height": (
                    "INT",
                    {"default": 1024, "min": CUSTOM_MIN, "max": CUSTOM_MAX, "step": 32},
                ),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    OUTPUT_IS_LIST = (False, False)
    FUNCTION = "calculate"
    CATEGORY = "MATRIX LAB/Resolution & Layout"

    def calculate(self, aspect_ratio, resolution_tier, custom_width, custom_height):
        return calculate_h3_resolution(
            aspect_ratio=aspect_ratio,
            resolution_tier=resolution_tier,
            custom_width=custom_width,
            custom_height=custom_height,
        )


__all__ = [
    "ASPECT_RATIOS",
    "CUSTOM_MAX",
    "CUSTOM_MIN",
    "H3ResolutionError",
    "MATRIX_H3Resolution",
    "RESOLUTION_TIERS",
    "calculate_h3_resolution",
]

