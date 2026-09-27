from decimal import Decimal

import pytest

from matrix_lab_nodes._core.wan3.pricing import estimate_cost


def test_default_generation_estimate_uses_dated_standard_720p_rate():
    result = estimate_cost(
        provider="WaveSpeed (billed)", operation="Text to Video", tier="Standard",
        resolution="720p", duration=5,
    )
    assert result.amount_usd == Decimal("0.50")
    assert "Estimate" in result.label and "2026-09-23" in result.label
    assert "$0.50" in result.label


@pytest.mark.parametrize("operation", ["Image to Video", "Extend Video"])
def test_i2v_spicy_and_extend_estimate_new_output_seconds_only(operation):
    result = estimate_cost(
        provider="WaveSpeed (billed)", operation=operation, tier="Prime",
        resolution="480p", duration=4, source_seconds=100,
    )
    assert result.amount_usd == Decimal("0.30")
    assert result.formula == "4 output seconds × $0.075/second"


def test_spicy_i2v_uses_the_same_dated_rate_without_cent_rounding():
    result = estimate_cost(
        provider="WaveSpeed (billed)", operation="Image to Video", image_variant="Spicy",
        tier="Prime", resolution="480p", duration=5,
    )
    assert result.amount_usd == Decimal("0.375")
    assert "$0.375 USD" in result.label


def test_reference_mode_unknown_source_duration_is_not_filled_in():
    result = estimate_cost(
        provider="WaveSpeed (billed)", operation="Reference to Video", tier="Standard",
        resolution="720p", duration=5, reference_seconds=None,
    )
    assert result.amount_usd is None
    assert "reference-video seconds (unknown) + 5 output seconds" in result.formula


def test_reference_mode_rounds_known_combined_source_up_and_includes_output():
    result = estimate_cost(
        provider="WaveSpeed (billed)", operation="Reference to Video", tier="Standard",
        resolution="720p", duration=5, reference_seconds=5.1,
    )
    assert result.amount_usd == Decimal("1.10")
    assert result.formula == "6 reference-video seconds + 5 output seconds, at $0.10/second"


@pytest.mark.parametrize(
    ("source", "edit_duration", "expected"),
    [(0.4, "Auto", Decimal("0.30")), (15.8, "Auto", Decimal("3.00")), (8.2, 5, Decimal("1.40"))],
)
def test_edit_normalizes_source_and_auto_ceil_clamp_output(source, edit_duration, expected):
    result = estimate_cost(
        provider="WaveSpeed (billed)", operation="Edit Video", tier="Standard",
        resolution="720p", duration=5, source_seconds=source, edit_duration=edit_duration,
    )
    assert result.amount_usd == expected


def test_edit_unknown_source_reports_formula_not_fake_amount():
    result = estimate_cost(
        provider="WaveSpeed (billed)", operation="Edit Video", tier="Prime",
        resolution="1080p", duration=5, source_seconds=None, edit_duration="Auto",
    )
    assert result.amount_usd is None
    assert "normalized source seconds (unknown) + Auto output seconds" in result.formula


def test_demo_is_free_fixture_and_invalid_finite_inputs_are_refused():
    result = estimate_cost(
        provider="Demo (free, offline)", operation="Edit Video", tier="Prime",
        resolution="1080p", duration=5, source_seconds=None,
    )
    assert result.amount_usd is None
    assert result.label == "Demo · free offline fixture"
    for value in (True, 2.5, float("nan"), float("inf"), 1, 31):
        with pytest.raises(ValueError):
            estimate_cost(
                provider="WaveSpeed (billed)", operation="Text to Video", tier="Standard",
                resolution="720p", duration=value,
            )
