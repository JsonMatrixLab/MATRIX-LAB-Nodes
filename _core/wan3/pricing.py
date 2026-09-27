"""Dated local cost estimates; never a live quote or provider request."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING

RATE_DATE = "2026-09-23"
_RATES = {
    ("Standard", "480p"): Decimal("0.05"),
    ("Standard", "720p"): Decimal("0.10"),
    ("Standard", "1080p"): Decimal("0.20"),
    ("Prime", "480p"): Decimal("0.075"),
    ("Prime", "720p"): Decimal("0.15"),
    ("Prime", "1080p"): Decimal("0.30"),
}
_OPERATIONS = {"Text to Video", "Image to Video", "Reference to Video", "Edit Video", "Extend Video"}


@dataclass(frozen=True)
class CostEstimate:
    label: str
    amount_usd: Decimal | None
    formula: str
    rate_per_second: Decimal | None
    rate_date: str = RATE_DATE


def _seconds(value, name: str, *, allow_zero: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number of seconds.")
    try:
        seconds = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{name} must be a finite number of seconds.") from exc
    if not seconds.is_finite() or seconds < 0 or (seconds == 0 and not allow_zero):
        raise ValueError(f"{name} must be a finite {'non-negative' if allow_zero else 'positive'} number of seconds.")
    return seconds


def _whole_seconds(seconds: Decimal) -> int:
    return int(seconds.to_integral_value(rounding=ROUND_CEILING))


def _money(seconds: int, rate: Decimal) -> Decimal:
    return (Decimal(seconds) * rate).quantize(Decimal("0.001"))


def _priced(formula: str, seconds: int, rate: Decimal) -> CostEstimate:
    amount = _money(seconds, rate)
    amount_text = f"{amount:.3f}".rstrip("0")
    if amount_text.endswith("."):
        amount_text += "0"
    elif "." in amount_text and len(amount_text.rsplit(".", 1)[1]) == 1:
        amount_text += "0"
    label = f"Estimate · ${amount_text} USD · rates dated {RATE_DATE}"
    return CostEstimate(label, amount, formula, rate)


def _unknown(formula: str, rate: Decimal) -> CostEstimate:
    return CostEstimate(f"Estimate · source duration unknown · rates dated {RATE_DATE}", None, formula, rate)


def estimate_cost(
    *,
    provider: str,
    operation: str,
    tier: str,
    resolution: str,
    duration: int,
    image_variant: str = "Regular",
    reference_seconds: int | float | Decimal | None = None,
    source_seconds: int | float | Decimal | None = None,
    edit_duration: int | str = "Auto",
) -> CostEstimate:
    """Estimate documented USD rates without network, media, or billing access.

    Reference seconds are totaled before documented whole-second rounding. Edit
    source time is rounded up and clamped to the documented 1–15 second range;
    Auto output is ceil(source duration), clamped to 2–15 seconds.
    """
    if provider not in ("Demo (free, offline)", "WaveSpeed (billed)"):
        raise ValueError("Select Demo (free, offline) or WaveSpeed (billed).")
    if operation not in _OPERATIONS:
        raise ValueError("Select a supported WAN 3.0 operation.")
    if image_variant not in ("Regular", "Spicy"):
        raise ValueError("Image route must be Regular or Spicy.")
    if image_variant == "Spicy" and operation not in ("Image to Video",):
        # Stale hidden values on other modes are deliberately ignored like the route builder.
        image_variant = "Regular"
    if tier not in ("Standard", "Prime"):
        raise ValueError("Tier must be Standard or Prime.")
    if resolution not in ("480p", "720p", "1080p"):
        raise ValueError("Resolution must be 480p, 720p, or 1080p.")
    if isinstance(duration, bool) or not isinstance(duration, int) or not 2 <= duration <= 30:
        raise ValueError("Output duration must be a whole number from 2 to 30 seconds.")
    ref = _seconds(reference_seconds, "Reference duration", allow_zero=True) if reference_seconds is not None else None
    source = _seconds(source_seconds, "Source duration") if source_seconds is not None else None
    if edit_duration != "Auto" and (isinstance(edit_duration, bool) or not isinstance(edit_duration, int) or not 2 <= edit_duration <= 15):
        raise ValueError("Edit output duration must be Auto or a whole number from 2 to 15 seconds.")
    if provider == "Demo (free, offline)":
        return CostEstimate("Demo · free offline fixture", None, "Local deterministic fixture; no provider request or upload.", None)

    rate = _RATES[(tier, resolution)]
    if operation in ("Text to Video", "Image to Video", "Extend Video"):
        return _priced(f"{duration} output seconds × ${rate}/second", duration, rate)
    if operation == "Reference to Video":
        if ref is None:
            return _unknown(f"reference-video seconds (unknown) + {duration} output seconds, at ${rate}/second", rate)
        billed_ref = _whole_seconds(ref)
        if billed_ref > 15:
            raise ValueError("Combined reference-video duration exceeds the 15-second route limit.")
        if billed_ref + duration > 30:
            raise ValueError("Reference-video seconds plus output duration exceed the 30-second route limit.")
        return _priced(f"{billed_ref} reference-video seconds + {duration} output seconds, at ${rate}/second", billed_ref + duration, rate)

    if source is None:
        if edit_duration == "Auto":
            formula = f"normalized source seconds (unknown) + Auto output seconds (ceil and clamp to 2–15), at ${rate}/second"
        else:
            formula = f"normalized source seconds (unknown) + {edit_duration} output seconds, at ${rate}/second"
        return _unknown(formula, rate)
    billed_source = min(15, max(1, _whole_seconds(source)))
    billed_output = edit_duration if isinstance(edit_duration, int) else min(15, max(2, _whole_seconds(source)))
    return _priced(f"{billed_source} normalized source seconds + {billed_output} output seconds, at ${rate}/second", billed_source + billed_output, rate)
