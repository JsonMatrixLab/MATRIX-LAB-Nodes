"""Simple influencer dimensions plus retained geometry for verified processing nodes."""

from dataclasses import dataclass

from ..resolution_dimensions import calculate_resolution


ASPECT_RATIOS = ("1:1", "9:16", "3:4")
RESOLUTION_TIERS = ("1K", "2K", "4K")
_LEGACY_RESOLUTION_TIERS = ("1K", "2K", "4K Progressive")
SPATIAL_ALIGNMENT = 16


class AIInfluencerResolutionError(ValueError):
    """The requested AI-influencer resolution plan is not supported."""


@dataclass(frozen=True, slots=True)
class ResolutionGeometry:
    """One immutable generation, detail, and delivery geometry.

    ``render_*`` keeps the shipped ABI name. It is the geometry presented to the
    detail path. Progressive 4K begins sampling at ``generation_*`` and transitions
    to ``render_*``; there is no final image upscaler in this contract.
    """

    aspect_ratio: str
    resolution_tier: str
    generation_width: int
    generation_height: int
    render_width: int
    render_height: int
    output_width: int
    output_height: int
    sampler_scales: str


_PLAN_TABLE = {
    ("1:1", "1K"): (2048, 2048, 2048, 2048, 1024, 1024, "1.0"),
    ("9:16", "1K"): (1152, 2048, 1152, 2048, 576, 1024, "1.0"),
    ("3:4", "1K"): (1536, 2048, 1536, 2048, 768, 1024, "1.0"),
    ("1:1", "2K"): (2048, 2048, 2048, 2048, 2048, 2048, "1.0"),
    ("9:16", "2K"): (1152, 2048, 1152, 2048, 1152, 2048, "1.0"),
    ("3:4", "2K"): (1536, 2048, 1536, 2048, 1536, 2048, "1.0"),
    ("1:1", "4K Progressive"): (2048, 2048, 4096, 4096, 4096, 4096, "0.5,1.0"),
    ("9:16", "4K Progressive"): (1152, 2048, 2304, 4096, 2304, 4096, "0.5,1.0"),
    ("3:4", "4K Progressive"): (1536, 2048, 3072, 4096, 3072, 4096, "0.5,1.0"),
}


def _require_choice(value, *, name, choices):
    if type(value) is not str or value not in choices:
        raise AIInfluencerResolutionError(f"{name} must be one of {choices}")


def _ratio_parts(aspect_ratio):
    left, right = aspect_ratio.split(":", 1)
    return int(left), int(right)


def validate_spatial_geometry(
    *,
    width,
    height,
    aspect_ratio,
    min_side,
    max_side,
    min_area,
    max_area,
    alignment=SPATIAL_ALIGNMENT,
):
    """Fail closed on type, alignment, side, area, and exact-ratio violations."""
    _require_choice(aspect_ratio, name="aspect_ratio", choices=ASPECT_RATIOS)
    values = {
        "width": width,
        "height": height,
        "min_side": min_side,
        "max_side": max_side,
        "min_area": min_area,
        "max_area": max_area,
        "alignment": alignment,
    }
    if any(type(value) is not int for value in values.values()):
        raise AIInfluencerResolutionError("geometry bounds and dimensions must be integers")
    if width <= 0 or height <= 0 or alignment <= 0:
        raise AIInfluencerResolutionError("dimensions and alignment must be positive")
    if min_side <= 0 or min_side > max_side or min_area <= 0 or min_area > max_area:
        raise AIInfluencerResolutionError("geometry bounds are invalid")
    if width % alignment or height % alignment:
        raise AIInfluencerResolutionError(
            f"dimensions must be divisible by {alignment}; got {width}x{height}"
        )
    if not min_side <= min(width, height) or max(width, height) > max_side:
        raise AIInfluencerResolutionError(
            f"dimensions {width}x{height} are outside side bounds {min_side}..{max_side}"
        )
    area = width * height
    if not min_area <= area <= max_area:
        raise AIInfluencerResolutionError(
            f"area {area} is outside bounds {min_area}..{max_area}"
        )
    ratio_width, ratio_height = _ratio_parts(aspect_ratio)
    if width * ratio_height != height * ratio_width:
        raise AIInfluencerResolutionError(
            f"dimensions {width}x{height} do not exactly match {aspect_ratio}"
        )
    return width, height


def validate_resolution_geometry(plan):
    """Validate a resolved plan without allocating a latent or image tensor."""
    if not isinstance(plan, ResolutionGeometry):
        raise AIInfluencerResolutionError("plan must be a ResolutionGeometry")
    _require_choice(plan.resolution_tier, name="resolution_tier", choices=_LEGACY_RESOLUTION_TIERS)
    validate_spatial_geometry(
        width=plan.generation_width,
        height=plan.generation_height,
        aspect_ratio=plan.aspect_ratio,
        min_side=1024,
        max_side=2048,
        min_area=1024 * 1024,
        max_area=2048 * 2048,
    )
    final_max = 4096 if plan.resolution_tier == "4K Progressive" else 2048
    validate_spatial_geometry(
        width=plan.render_width,
        height=plan.render_height,
        aspect_ratio=plan.aspect_ratio,
        min_side=1024,
        max_side=final_max,
        min_area=1024 * 1024,
        max_area=final_max * final_max,
    )
    validate_spatial_geometry(
        width=plan.output_width,
        height=plan.output_height,
        aspect_ratio=plan.aspect_ratio,
        min_side=576,
        max_side=final_max,
        min_area=576 * 1024,
        max_area=final_max * final_max,
    )
    expected_scales = "0.5,1.0" if plan.resolution_tier == "4K Progressive" else "1.0"
    if plan.sampler_scales != expected_scales:
        raise AIInfluencerResolutionError(
            f"{plan.resolution_tier} requires sampler_scales={expected_scales}"
        )
    if plan.resolution_tier == "4K Progressive":
        if (plan.render_width, plan.render_height) != (
            plan.generation_width * 2,
            plan.generation_height * 2,
        ):
            raise AIInfluencerResolutionError(
                "4K Progressive render geometry must be exactly twice generation geometry"
            )
    elif (plan.render_width, plan.render_height) != (
        plan.generation_width,
        plan.generation_height,
    ):
        raise AIInfluencerResolutionError(
            "non-progressive render geometry must equal generation geometry"
        )
    if plan.resolution_tier != "1K" and (
        plan.output_width,
        plan.output_height,
    ) != (plan.render_width, plan.render_height):
        raise AIInfluencerResolutionError(
            "2K and 4K delivery geometry must equal detail geometry"
        )
    return plan


def resolve_resolution_geometry(*, aspect_ratio, resolution_tier):
    """Resolve and validate one row from the fixed compatibility table."""
    _require_choice(aspect_ratio, name="aspect_ratio", choices=ASPECT_RATIOS)
    _require_choice(resolution_tier, name="resolution_tier", choices=_LEGACY_RESOLUTION_TIERS)
    plan = ResolutionGeometry(
        aspect_ratio,
        resolution_tier,
        *_PLAN_TABLE[(aspect_ratio, resolution_tier)],
    )
    return validate_resolution_geometry(plan)


def calculate_ai_influencer_resolution(*, aspect_ratio, resolution_tier):
    """Return only width and height, with the selected tier as the exact long edge."""
    _require_choice(aspect_ratio, name="aspect_ratio", choices=ASPECT_RATIOS)
    _require_choice(resolution_tier, name="resolution_tier", choices=RESOLUTION_TIERS)
    return calculate_resolution(aspect_ratio=aspect_ratio, resolution_tier=resolution_tier)


def execute_utility_operation(item):
    """Execute one compiler-provided AI-influencer resolution payload."""
    if not isinstance(item, dict):
        raise AIInfluencerResolutionError("a payload item must be a mapping")
    required = {"aspect_ratio", "resolution_tier"}
    if set(item) != required:
        raise AIInfluencerResolutionError(
            "a payload item must contain exactly: aspect_ratio, resolution_tier"
        )
    return calculate_ai_influencer_resolution(**item)


__all__ = [
    "AIInfluencerResolutionError",
    "ASPECT_RATIOS",
    "RESOLUTION_TIERS",
    "ResolutionGeometry",
    "SPATIAL_ALIGNMENT",
    "calculate_ai_influencer_resolution",
    "execute_utility_operation",
    "resolve_resolution_geometry",
    "validate_resolution_geometry",
    "validate_spatial_geometry",
]
