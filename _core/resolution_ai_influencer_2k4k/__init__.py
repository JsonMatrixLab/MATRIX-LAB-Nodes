"""AI-influencer pixel dimensions restricted to the 2K and 4K tiers."""

from ..resolution_ai_influencer import (
    AIInfluencerResolutionError,
    ASPECT_RATIOS,
    calculate_ai_influencer_resolution as _calculate_ai_influencer_resolution,
)


RESOLUTION_TIERS = ("2K", "4K")


def calculate_ai_influencer_resolution_2k4k(*, aspect_ratio, resolution_tier):
    """Return width and height for an approved aspect ratio and 2K/4K tier."""
    if type(resolution_tier) is not str or resolution_tier not in RESOLUTION_TIERS:
        raise AIInfluencerResolutionError(
            f"resolution_tier must be one of {RESOLUTION_TIERS}"
        )
    return _calculate_ai_influencer_resolution(
        aspect_ratio=aspect_ratio,
        resolution_tier=resolution_tier,
    )


def execute_utility_operation(item):
    """Execute one compiler-provided 2K/4K resolution payload."""
    if not isinstance(item, dict):
        raise AIInfluencerResolutionError("a payload item must be a mapping")
    if set(item) != {"aspect_ratio", "resolution_tier"}:
        raise AIInfluencerResolutionError(
            "a payload item must contain exactly: aspect_ratio, resolution_tier"
        )
    return calculate_ai_influencer_resolution_2k4k(**item)


__all__ = [
    "AIInfluencerResolutionError",
    "ASPECT_RATIOS",
    "RESOLUTION_TIERS",
    "calculate_ai_influencer_resolution_2k4k",
    "execute_utility_operation",
]
