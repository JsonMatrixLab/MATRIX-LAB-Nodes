"""Model-independent pixel dimensions for preset tiers and custom sizes."""

ASPECT_RATIOS = {
    "1:1": (1, 1), "16:9": (16, 9), "9:16": (9, 16),
    "4:3": (4, 3), "3:4": (3, 4), "3:2": (3, 2),
    "2:3": (2, 3), "4:5": (4, 5),
}
RESOLUTION_TIERS = {"1K": 1024, "2K": 2048, "4K": 4096}
MIN_CUSTOM_DIMENSION = 1
MAX_DIMENSION = 16384


class ResolutionDimensionsError(ValueError):
    """The requested dimensions are malformed or out of bounds."""


def calculate_resolution(*, aspect_ratio, resolution_tier, custom_width=2048, custom_height=2048):
    """Keep the long edge exact and round the short edge to nearest integer, ties up.

    Dimensions are pixel geometry, not a claim of any model's supported input size.
    Custom values are preserved exactly without an implicit alignment rule.
    """
    if type(aspect_ratio) is not str or aspect_ratio not in (*ASPECT_RATIOS, "Custom"):
        raise ResolutionDimensionsError("unsupported aspect_ratio")
    if type(resolution_tier) is not str or resolution_tier not in RESOLUTION_TIERS:
        raise ResolutionDimensionsError("resolution_tier must be one of 1K, 2K, 4K")
    if aspect_ratio == "Custom":
        for name, value in (("custom_width", custom_width), ("custom_height", custom_height)):
            if type(value) is not int or not MIN_CUSTOM_DIMENSION <= value <= MAX_DIMENSION:
                raise ResolutionDimensionsError(f"{name} must be an integer in 1..{MAX_DIMENSION}")
        return custom_width, custom_height
    width_ratio, height_ratio = ASPECT_RATIOS[aspect_ratio]
    long_side = RESOLUTION_TIERS[resolution_tier]
    long_ratio, short_ratio = max(width_ratio, height_ratio), min(width_ratio, height_ratio)
    short_side = (2 * long_side * short_ratio + long_ratio) // (2 * long_ratio)
    return (long_side, short_side) if width_ratio >= height_ratio else (short_side, long_side)


def execute_utility_operation(item):
    """Execute one compiler-provided resolution payload."""
    required = {"aspect_ratio", "resolution_tier", "custom_width", "custom_height"}
    if not isinstance(item, dict) or set(item) != required:
        raise ResolutionDimensionsError("a payload item must contain exactly: " + ", ".join(sorted(required)))
    return calculate_resolution(**item)


__all__ = [
    "ASPECT_RATIOS", "RESOLUTION_TIERS", "MIN_CUSTOM_DIMENSION", "MAX_DIMENSION",
    "ResolutionDimensionsError", "calculate_resolution", "execute_utility_operation",
]
