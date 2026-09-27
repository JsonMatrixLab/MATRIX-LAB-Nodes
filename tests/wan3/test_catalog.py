import pytest

from matrix_lab_nodes._core.wan3.catalog import (
    ROUTES,
    ContractError,
    build_payload,
    selected_route,
)


def test_exact_twelve_route_inventory():
    expected = {
        "alibaba/wan-3.0/text-to-video",
        "alibaba/wan-3.0-prime/text-to-video",
        "alibaba/wan-3.0/image-to-video",
        "alibaba/wan-3.0-prime/image-to-video",
        "alibaba/wan-3.0/image-to-video-spicy",
        "alibaba/wan-3.0-prime/image-to-video-spicy",
        "alibaba/wan-3.0/reference-to-video",
        "alibaba/wan-3.0-prime/reference-to-video",
        "alibaba/wan-3.0/video-edit",
        "alibaba/wan-3.0-prime/video-edit",
        "alibaba/wan-3.0/video-extend",
        "alibaba/wan-3.0-prime/video-extend",
    }
    assert {route.model_id for route in ROUTES.values()} == expected


@pytest.mark.parametrize("resolution", ["480p", "720p", "1080p"])
@pytest.mark.parametrize("aspect", ["16:9", "9:16", "1:1", "4:3", "3:4"])
def test_valid_resolution_aspect_audio_and_expansion_values(resolution, aspect):
    _route, payload = build_payload(
        operation="Text to Video", tier="Prime",
        values={"prompt": "A scene", "resolution": resolution, "aspect_ratio": aspect,
                "enable_audio": False, "enable_prompt_expansion": True, "seed_mode": "Fixed", "seed": 2_147_483_647},
    )
    assert payload["resolution"] == resolution
    assert payload["aspect_ratio"] == aspect
    assert payload["enable_audio"] is False
    assert payload["enable_prompt_expansion"] is True
    assert payload["seed"] == 2_147_483_647


@pytest.mark.parametrize("tier", ["Standard", "Prime"])
@pytest.mark.parametrize(
    ("operation", "variant", "media", "expected_fields"),
    [
        ("Text to Video", "Regular", {}, {"prompt", "resolution", "seed", "enable_prompt_expansion", "duration", "enable_audio", "aspect_ratio"}),
        ("Image to Video", "Regular", {"image": "https://asset.invalid/first"}, {"prompt", "image", "resolution", "seed", "enable_prompt_expansion", "duration", "enable_audio"}),
        ("Image to Video", "Spicy", {"image": "https://asset.invalid/first"}, {"image", "resolution", "seed", "enable_prompt_expansion", "duration", "enable_audio"}),
        ("Reference to Video", "Regular", {"reference_images": ["img"], "reference_videos": ["vid"], "reference_audios": ["aud"]}, {"prompt", "resolution", "seed", "enable_prompt_expansion", "duration", "enable_audio", "aspect_ratio", "reference_images", "reference_videos", "reference_audios"}),
        ("Edit Video", "Regular", {"video": "https://asset.invalid/video"}, {"prompt", "video", "resolution", "seed", "enable_prompt_expansion", "generate_audio"}),
        ("Extend Video", "Regular", {"video": "https://asset.invalid/video"}, {"prompt", "video", "resolution", "seed", "enable_prompt_expansion", "duration", "enable_audio"}),
    ],
)
def test_each_concrete_route_emits_only_its_allowed_fields(tier, operation, variant, media, expected_fields):
    values = {"prompt": "A quiet street at dawn", "resolution": "720p", "seed_mode": "Fixed", "seed": 123, "duration": 5, "aspect_ratio": "16:9"}
    if operation == "Image to Video":
        values["aspect_ratio"] = "Auto"
    if operation == "Image to Video" and variant == "Spicy":
        values.pop("prompt")
    route, payload = build_payload(operation=operation, tier=tier, variant=variant, values=values, media=media)
    assert set(payload) == expected_fields
    assert set(payload) <= route.allowed
    assert route.model_id.startswith("alibaba/wan-3.0")
    assert route.model_id.split("/")[1].startswith("wan-3.0-prime" if tier == "Prime" else "wan-3.0")
    assert "Auto" not in payload.values()


def test_i2v_auto_aspect_is_omitted_and_spicy_prompt_is_optional():
    _, payload = build_payload(
        operation="Image to Video", tier="Standard", variant="Spicy",
        values={"aspect_ratio": "Auto", "seed_mode": "Random"}, media={"image": "asset"},
    )
    assert "prompt" not in payload
    assert "aspect_ratio" not in payload
    assert payload["seed"] == -1


def test_hidden_i2v_preferences_do_not_leak_after_switching_to_nonimage_mode():
    values = {"prompt": "A scene", "duration": 5, "aspect_ratio": "Auto", "seed_mode": "Fixed", "seed": 3}
    image_route, _ = build_payload(
        operation="Image to Video", tier="Standard", variant="Spicy",
        values=values, media={"image": "first-frame"},
    )
    text_route, text_payload = build_payload(
        operation="Text to Video", tier="Standard", variant="Spicy",
        values=values, media={},
    )
    assert image_route.model_id.endswith("image-to-video-spicy")
    assert text_route.model_id.endswith("text-to-video")
    assert text_payload["aspect_ratio"] == "16:9"


def test_edit_auto_duration_is_omitted_and_audio_uses_provider_field_name():
    _, payload = build_payload(
        operation="Edit Video", tier="Prime", values={"prompt": "Keep the camera still", "edit_duration": "Auto", "generate_audio": False},
        media={"video": "asset"},
    )
    assert "duration" not in payload
    assert payload["generate_audio"] is False
    assert "enable_audio" not in payload


def test_extend_duration_means_new_segment_and_ignores_inactive_controls():
    _, payload = build_payload(
        operation="Extend Video", tier="Standard",
        values={"prompt": "Continue", "duration": 9, "aspect_ratio": "1:1", "enable_audio": True},
        media={"video": "source"},
    )
    assert payload["duration"] == 9
    assert "aspect_ratio" not in payload


def test_reference_order_is_preserved_and_limits_are_checked_before_encoding():
    ordered = [f"image-{i}" for i in range(10)]
    _, payload = build_payload(
        operation="Reference to Video", tier="Standard", values={"prompt": "Use in order"},
        media={"reference_images": ordered},
    )
    assert payload["reference_images"] == ordered
    with pytest.raises(ContractError, match="At most 10"):
        build_payload(
            operation="Reference to Video", tier="Standard", values={"prompt": "Use in order"},
            media={"reference_images": ordered + ["image-10"]},
        )


@pytest.mark.parametrize("operation,media", [("Text to Video", {"image": "wrong"}), ("Image to Video", {"video": "wrong"}), ("Reference to Video", {"video": "wrong"}), ("Edit Video", {"image": "wrong"}), ("Extend Video", {"reference_images": ["wrong"]})])
def test_incompatible_media_is_refused_by_the_backend(operation, media):
    values = {"prompt": "A prompt"}
    if operation in ("Edit Video", "Extend Video"):
        media.setdefault("video", "source")
    with pytest.raises(ContractError, match="incompatible"):
        build_payload(operation=operation, tier="Standard", values=values, media=media)


@pytest.mark.parametrize("duration", [1, 31, 5.5, True, float("nan")])
def test_generate_duration_rejects_invalid_numbers(duration):
    with pytest.raises(ContractError):
        build_payload(operation="Text to Video", tier="Standard", values={"prompt": "Run", "duration": duration})


@pytest.mark.parametrize("seed", [-1, 2_147_483_648, 1.5, True])
def test_fixed_seed_rejects_values_outside_conservative_ui_contract(seed):
    with pytest.raises(ContractError):
        build_payload(operation="Text to Video", tier="Standard", values={"prompt": "Run", "seed_mode": "Fixed", "seed": seed})


def test_unknown_mode_tier_variant_and_missing_required_inputs_refuse():
    for args in (
        {"operation": "Image", "tier": "Standard"},
        {"operation": "Text to Video", "tier": "Other"},
        {"operation": "Image to Video", "tier": "Standard", "variant": "Spicier"},
    ):
        with pytest.raises(ContractError):
            selected_route(**args)
    with pytest.raises(ContractError, match="requires"):
        build_payload(operation="Text to Video", tier="Standard", values={"prompt": "   "})
    with pytest.raises(ContractError, match="Connect a source"):
        build_payload(operation="Edit Video", tier="Standard", values={"prompt": "edit"})


def test_reference_operation_requires_at_least_one_reference():
    with pytest.raises(ContractError, match="at least one"):
        build_payload(operation="Reference to Video", tier="Standard", values={"prompt": "Use a reference"})
