"""FLUX 3 Klein exact resolution table and ComfyUI utility node."""

from __future__ import annotations


ASPECT_RATIOS = ("1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16")
RESOLUTIONS = ("1K", "1.5K", "2K", "4K")
TIER_SIDE = {"1K": 1024, "1.5K": 1536, "2K": 2048, "4K": 4096}
SIZES = {
    "1K": {
        "1:1": (1024, 1024), "4:3": (1184, 880), "3:4": (880, 1184), "3:2": (1248, 832), "2:3": (832, 1248), "16:9": (1360, 768), "9:16": (768, 1360),
    },
    "1.5K": {
        "1:1": (1536, 1536), "4:3": (1776, 1328), "3:4": (1328, 1776), "3:2": (1888, 1248), "2:3": (1248, 1888), "16:9": (2048, 1152), "9:16": (1152, 2048),
    },
    "2K": {
        "1:1": (2048, 2048), "4:3": (2352, 1776), "3:4": (1776, 2352), "3:2": (2496, 1680), "2:3": (1680, 2496), "16:9": (2720, 1536), "9:16": (1536, 2720),
    },
    "4K": {
        "1:1": (4096, 4096), "4:3": (4096, 3088), "3:4": (3088, 4096), "3:2": (4096, 2752), "2:3": (2752, 4096), "16:9": (4096, 2320), "9:16": (2320, 4096),
    },
}
GRID = 16
MAX_LONGEST_SIDE = 4096


class Flux3KleinResolutionError(ValueError):
    """The requested FLUX 3 Klein geometry is invalid or unsupported."""


def validate_flux_3_klein_dimensions(width, height, resolution):
    """Validate and return width and height against the tier's hard limits."""
    if type(width) is not int or type(height) is not int:
        raise Flux3KleinResolutionError("width and height must be integers")
    if resolution not in SIZES:
        raise Flux3KleinResolutionError(f"resolution must be one of {RESOLUTIONS}")
    if width <= 0 or height <= 0 or width % GRID or height % GRID:
        raise Flux3KleinResolutionError("width and height must be positive multiples of 16")
    if max(width, height) > MAX_LONGEST_SIDE:
        raise Flux3KleinResolutionError(
            f"longest dimension must be at most {MAX_LONGEST_SIDE}"
        )
    max_area = TIER_SIDE[resolution] ** 2
    if width * height > max_area:
        raise Flux3KleinResolutionError(f"pixel area must be at most {max_area}")
    return width, height


def calculate_flux_3_klein_resolution(*, aspect_ratio, resolution):
    """Return only the exact size selected from the frozen 28-cell table."""
    if type(aspect_ratio) is not str or aspect_ratio not in ASPECT_RATIOS:
        raise Flux3KleinResolutionError(f"aspect_ratio must be one of {ASPECT_RATIOS}")
    if type(resolution) is not str or resolution not in SIZES:
        raise Flux3KleinResolutionError(f"resolution must be one of {RESOLUTIONS}")
    return validate_flux_3_klein_dimensions(*SIZES[resolution][aspect_ratio], resolution)


def execute_utility_operation(item):
    """Execute the compiler's exact FLUX 3 Klein resolution payload."""
    if not isinstance(item, dict) or set(item) != {"aspect_ratio", "resolution"}:
        raise Flux3KleinResolutionError(
            "a FLUX 3 Klein resolution payload needs exactly aspect_ratio and resolution"
        )
    return calculate_flux_3_klein_resolution(**item)


class MATRIX_Flux3KleinResolution:
    """Geometry-only utility for the FLUX 3 Klein exact sizes."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "aspect_ratio": (list(ASPECT_RATIOS), {"default": "1:1"}),
                "resolution": (list(RESOLUTIONS), {"default": "1K"}),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    OUTPUT_IS_LIST = (False, False)
    FUNCTION = "calculate"
    CATEGORY = "MATRIX LAB/Resolution & Layout"

    def calculate(self, aspect_ratio, resolution):
        return calculate_flux_3_klein_resolution(
            aspect_ratio=aspect_ratio, resolution=resolution
        )


__all__ = [
    "ASPECT_RATIOS",
    "GRID",
    "MAX_LONGEST_SIDE",
    "RESOLUTIONS",
    "MATRIX_Flux3KleinResolution",
    "SIZES",
    "Flux3KleinResolutionError",
    "calculate_flux_3_klein_resolution",
    "execute_utility_operation",
    "validate_flux_3_klein_dimensions",
]
