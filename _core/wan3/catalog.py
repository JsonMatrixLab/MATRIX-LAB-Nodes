"""Frozen WaveSpeed WAN 3.0 route contracts from the 2026-09-23 catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


TIERS = ("Standard", "Prime")
OPERATIONS = ("Text to Video", "Image to Video", "Reference to Video", "Edit Video", "Extend Video")
RESOLUTIONS = ("480p", "720p", "1080p")
ASPECT_RATIOS = ("16:9", "9:16", "1:1", "4:3", "3:4")
IMAGE_VARIANTS = ("Regular", "Spicy")


@dataclass(frozen=True)
class Route:
    operation: str
    tier: str
    variant: str
    model_id: str
    allowed: frozenset[str]
    required: frozenset[str]


_ROUTE_FIELDS: dict[str, tuple[set[str], set[str]]] = {
    "Text to Video": (
        {"prompt", "resolution", "duration", "aspect_ratio", "enable_audio", "enable_prompt_expansion", "seed"},
        {"prompt"},
    ),
    "Image to Video": (
        {"prompt", "image", "last_image", "resolution", "duration", "aspect_ratio", "enable_audio", "enable_prompt_expansion", "seed"},
        {"prompt", "image"},
    ),
    "Reference to Video": (
        {"prompt", "resolution", "duration", "aspect_ratio", "enable_audio", "enable_prompt_expansion", "seed", "reference_images", "reference_videos", "reference_audios"},
        {"prompt"},
    ),
    "Edit Video": (
        {"prompt", "video", "resolution", "duration", "generate_audio", "enable_prompt_expansion", "seed", "reference_images", "reference_audios"},
        {"prompt", "video"},
    ),
    "Extend Video": (
        {"prompt", "video", "last_image", "resolution", "duration", "enable_audio", "enable_prompt_expansion", "seed"},
        {"prompt", "video"},
    ),
}


def _routes() -> dict[tuple[str, str, str], Route]:
    result: dict[tuple[str, str, str], Route] = {}
    for operation in OPERATIONS:
        for tier in TIERS:
            variants = IMAGE_VARIANTS if operation == "Image to Video" else ("Regular",)
            for variant in variants:
                model = "alibaba/wan-3.0"
                if tier == "Prime":
                    model += "-prime"
                suffix = {
                    "Text to Video": "text-to-video",
                    "Image to Video": "image-to-video" if variant == "Regular" else "image-to-video-spicy",
                    "Reference to Video": "reference-to-video",
                    "Edit Video": "video-edit",
                    "Extend Video": "video-extend",
                }[operation]
                allowed, required = _ROUTE_FIELDS[operation]
                result[(operation, tier, variant)] = Route(
                    operation=operation,
                    tier=tier,
                    variant=variant,
                    model_id=f"{model}/{suffix}",
                    allowed=frozenset(allowed),
                    required=frozenset(required - ({"prompt"} if variant == "Spicy" else set())),
                )
    return result


ROUTES = _routes()
assert len(ROUTES) == 12


class ContractError(ValueError):
    """The selected route cannot represent the supplied inputs."""


def selected_route(operation: str, tier: str, variant: str = "Regular") -> Route:
    try:
        return ROUTES[(operation, tier, variant)]
    except (KeyError, TypeError) as exc:
        raise ContractError("Choose a supported operation, tier, and image route variant.") from exc


def _strict_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{name} must be a whole number.")
    if not minimum <= value <= maximum:
        raise ContractError(f"{name} must be between {minimum} and {maximum}.")
    return value


def build_payload(
    *,
    operation: str,
    tier: str,
    variant: str = "Regular",
    values: Mapping[str, Any],
    media: Mapping[str, Any] | None = None,
) -> tuple[Route, dict[str, Any]]:
    """Build a new exact-route payload; inactive controls never leak into it."""
    # Spicy is an I2V-only route choice. Preserve it in the UI as a local
    # preference, but normalize it away while another operation is selected.
    effective_variant = variant if operation == "Image to Video" else "Regular"
    route = selected_route(operation, tier, effective_variant)
    media = media or {}
    media_roles = {
        "Text to Video": {"image", "last_image", "video", "reference_images", "reference_videos", "reference_audios"},
        "Image to Video": {"video", "reference_images", "reference_videos", "reference_audios"},
        "Reference to Video": {"image", "last_image", "video"},
        "Edit Video": {"image", "last_image", "reference_videos"},
        "Extend Video": {"image", "reference_images", "reference_videos", "reference_audios"},
    }[operation]
    conflicts = sorted(key for key in media_roles if media.get(key))
    if conflicts:
        raise ContractError("Connected media is incompatible with this operation: " + ", ".join(conflicts) + ".")

    prompt = values.get("prompt", "")
    if not isinstance(prompt, str):
        raise ContractError("Prompt must be text.")
    payload: dict[str, Any] = {}
    if prompt.strip():
        payload["prompt"] = prompt
    elif "prompt" in route.required:
        raise ContractError("This route requires a non-empty prompt.")

    resolution = values.get("resolution", "720p")
    if resolution not in RESOLUTIONS:
        raise ContractError("Resolution must be 480p, 720p, or 1080p.")
    payload["resolution"] = resolution

    # Optional seed accepts the documented -1 sentinel and conservative fixed range.
    if values.get("seed_mode", "Random") == "Fixed":
        payload["seed"] = _strict_int(values.get("seed", 0), "Seed", 0, 2_147_483_647)
    elif values.get("seed_mode", "Random") == "Random":
        payload["seed"] = -1
    else:
        raise ContractError("Seed mode must be Random or Fixed.")

    if "enable_prompt_expansion" in route.allowed:
        payload["enable_prompt_expansion"] = _strict_bool(values, "enable_prompt_expansion", False)

    if operation in ("Text to Video", "Image to Video", "Reference to Video", "Extend Video"):
        payload["duration"] = _strict_int(values.get("duration", 5), "Duration", 2, 30)
        payload["enable_audio"] = _strict_bool(values, "enable_audio", True)
    elif operation == "Edit Video":
        payload["generate_audio"] = _strict_bool(values, "generate_audio", True)
        edit_duration = values.get("edit_duration", "Auto")
        if edit_duration != "Auto":
            payload["duration"] = _strict_int(edit_duration, "Edit duration", 2, 15)

    if operation in ("Text to Video", "Image to Video", "Reference to Video"):
        aspect = values.get("aspect_ratio", "Auto" if operation == "Image to Video" else "16:9")
        if operation == "Image to Video" and aspect == "Auto":
            pass  # Omission requests input-image adaptation; "Auto" is not a provider value.
        elif operation in ("Text to Video", "Reference to Video") and aspect == "Auto":
            payload["aspect_ratio"] = "16:9"
        elif aspect in ASPECT_RATIOS:
            payload["aspect_ratio"] = aspect
        else:
            raise ContractError("Choose Auto or one of the supported aspect ratios.")

    media_fields = {
        "Image to Video": {"image": "image", "last_image": "last_image"},
        "Reference to Video": {
            "reference_images": "reference_images",
            "reference_videos": "reference_videos",
            "reference_audios": "reference_audios",
        },
        "Edit Video": {"video": "video", "reference_images": "reference_images", "reference_audios": "reference_audios"},
        "Extend Video": {"video": "video", "last_image": "last_image"},
    }.get(operation, {})
    for source_name, api_name in media_fields.items():
        value = media.get(source_name)
        if value is None or (isinstance(value, list) and not value):
            continue
        if api_name.startswith("reference_"):
            if not isinstance(value, list):
                raise ContractError(f"{source_name} must be an ordered list.")
            limit = {"reference_images": 10, "reference_videos": 5, "reference_audios": 5}[api_name]
            if len(value) > limit:
                raise ContractError(f"At most {limit} {source_name.replace('_', ' ')} are supported.")
            payload[api_name] = value
        else:
            payload[api_name] = value

    if operation == "Reference to Video":
        if not any(payload.get(name) for name in ("reference_images", "reference_videos", "reference_audios")):
            raise ContractError("Reference to Video needs at least one image, video, or audio reference.")
    if operation in ("Edit Video", "Extend Video") and media.get("video") is None:
        raise ContractError("Connect a source VIDEO for this operation.")

    unknown = set(payload) - route.allowed
    missing = route.required - set(payload)
    if unknown or missing:
        raise ContractError(f"Internal route contract mismatch (unknown={sorted(unknown)}, missing={sorted(missing)}).")
    return route, payload


def _strict_bool(values: Mapping[str, Any], key: str, default: bool) -> bool:
    value = values.get(key, default)
    if not isinstance(value, bool):
        raise ContractError(f"{key} must be true or false.")
    return value
