"""Ordered local image records and the native-list postprocessing adapter."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from ..easy_crop import EasyCropValidationError, crop_image, resolve_image_path


STATE_VERSION = 1
MAX_IMAGES = 10
EMPTY_STATE_JSON = '{"version":1,"items":[],"selected":null}'


class ImageCollectionValidationError(ValueError):
    """Fail-closed refusal for invalid state or an unreadable collection asset."""

    code = "MATRIX_IMAGE_COLLECTION_VALIDATION"


@dataclass(frozen=True)
class CollectionItem:
    """One durable ComfyUI input-relative identity."""

    image: str


@dataclass(frozen=True)
class CollectionState:
    """Ordered saved state independent of any eventual execution consumer."""

    items: tuple[CollectionItem, ...]
    selected: int | None
    version: int = STATE_VERSION


@dataclass(frozen=True)
class ImageRecord:
    """One independently decoded RGB image and alpha-derived mask."""

    image: str
    image_tensor: Any
    mask_tensor: Any
    width: int
    height: int


def _reject_duplicate_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ImageCollectionValidationError(f"Duplicate JSON field: {key!r}.")
        result[key] = value
    return result


def _input_relative_path(identity: str) -> PurePosixPath:
    if not isinstance(identity, str) or "\x00" in identity:
        raise ImageCollectionValidationError("Image identity must be a string.")
    suffix = " [input]"
    if not identity.endswith(suffix):
        raise ImageCollectionValidationError(
            "Image identity must use the explicit ComfyUI [input] annotation."
        )
    relative = identity[: -len(suffix)]
    if not relative or "\\" in relative or relative.startswith("/"):
        raise ImageCollectionValidationError("Image identity is not input-relative.")
    if any(part in ("", ".", "..") for part in relative.split("/")):
        raise ImageCollectionValidationError("Image identity is not input-relative.")
    path = PurePosixPath(relative)
    if path.is_absolute():
        raise ImageCollectionValidationError("Image identity is not input-relative.")
    if ":" in path.parts[0]:
        raise ImageCollectionValidationError("Image identity is not input-relative.")
    return path


def canonical_state_json(state: CollectionState) -> str:
    """Serialize state with one stable key order and no insignificant whitespace."""

    encoded = json.dumps(
        {
            "version": STATE_VERSION,
            "items": [{"image": item.image} for item in state.items],
            "selected": state.selected,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    parse_collection_state(encoded)
    return encoded


def parse_collection_state(value: str) -> CollectionState:
    """Parse and strictly validate the canonical collection state structure."""

    if not isinstance(value, str):
        raise ImageCollectionValidationError("Collection state must be a JSON string.")
    try:
        value.encode("utf-8")
        data = json.loads(value, object_pairs_hook=_reject_duplicate_fields)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ImageCollectionValidationError("Collection state is not valid JSON.") from exc
    if not isinstance(data, dict) or set(data) != {"version", "items", "selected"}:
        raise ImageCollectionValidationError(
            "Collection state must contain exactly version, items, and selected."
        )
    if type(data["version"]) is not int or data["version"] != STATE_VERSION:
        raise ImageCollectionValidationError(
            f"Unsupported collection state version: {data['version']!r}."
        )
    raw_items = data["items"]
    if not isinstance(raw_items, list):
        raise ImageCollectionValidationError("Collection items must be an array.")
    if len(raw_items) > MAX_IMAGES:
        raise ImageCollectionValidationError(f"Collection supports 1–{MAX_IMAGES} images.")
    items: list[CollectionItem] = []
    identities: set[str] = set()
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict) or set(raw) != {"image"}:
            raise ImageCollectionValidationError(
                f"Collection item {index + 1} must contain exactly image."
            )
        identity = raw["image"]
        _input_relative_path(identity)
        if identity in identities:
            raise ImageCollectionValidationError(
                f"Collection item {index + 1} duplicates an existing image identity."
            )
        identities.add(identity)
        items.append(CollectionItem(image=identity))
    selected = data["selected"]
    if selected is not None and (
        type(selected) is not int or selected < 0 or selected >= len(items)
    ):
        raise ImageCollectionValidationError(
            "Selected index must be null or identify an existing collection item."
        )
    if not items and selected is not None:
        raise ImageCollectionValidationError("An empty collection cannot have a selection.")
    return CollectionState(items=tuple(items), selected=selected)


def _verify_owned_input(identity: str, folder_paths_module=None) -> Path:
    _input_relative_path(identity)
    try:
        resolved = resolve_image_path(identity, folder_paths_module)
        paths = folder_paths_module
        if paths is None:
            import folder_paths as paths  # type: ignore[no-redef]
        input_root = Path(paths.get_input_directory()).resolve(strict=True)
        resolved.relative_to(input_root)
    except ImageCollectionValidationError:
        raise
    except (EasyCropValidationError, ImportError, OSError, TypeError, ValueError) as exc:
        raise ImageCollectionValidationError(f"Missing image: {identity}") from exc
    return resolved


def load_ordered_records(
    value: str,
    *,
    folder_paths_module=None,
    decoder: Callable[..., tuple[Any, Any]] = crop_image,
) -> tuple[ImageRecord, ...]:
    """Decode every item in saved order without batching, resizing, or cursor state."""

    state = parse_collection_state(value)
    records: list[ImageRecord] = []
    for index, item in enumerate(state.items):
        _verify_owned_input(item.image, folder_paths_module)
        try:
            image_tensor, mask_tensor = decoder(
                item.image, "Free", 1, 1, 0, 0, 1, 1
            )
        except EasyCropValidationError as exc:
            message = str(exc)
            if "Animated images" in message:
                reason = "Animated image is unsupported"
            elif "could not be decoded" in message:
                reason = "Corrupt or unreadable image"
            else:
                reason = message.rstrip(".")
            raise ImageCollectionValidationError(
                f"Collection item {index + 1} ({item.image}): {reason}."
            ) from exc
        try:
            shape = tuple(image_tensor.shape)
            mask_shape = tuple(mask_tensor.shape)
            height, width = int(shape[1]), int(shape[2])
        except (AttributeError, IndexError, TypeError, ValueError) as exc:
            raise ImageCollectionValidationError(
                f"Collection item {index + 1} ({item.image}) decoded to an invalid record."
            ) from exc
        if len(shape) != 4 or shape[0] != 1 or shape[3] != 3 or mask_shape != (1, height, width):
            raise ImageCollectionValidationError(
                f"Collection item {index + 1} ({item.image}) decoded to an invalid record."
            )
        records.append(
            ImageRecord(
                image=item.image,
                image_tensor=image_tensor,
                mask_tensor=mask_tensor,
                width=width,
                height=height,
            )
        )
    return tuple(records)


def execute_utility_operation(inputs):
    """Process every saved item, preserving native list order and individual sizes."""
    if not isinstance(inputs, dict) or set(inputs) != {"collection"}:
        raise ImageCollectionValidationError("Image Batch Loader requires exactly collection.")
    state = parse_collection_state(inputs["collection"])
    if not state.items:
        raise ImageCollectionValidationError("Add at least one image before running the collection.")
    records = load_ordered_records(inputs["collection"])
    # ComfyUI maps normal downstream IMAGE/MASK inputs over these parallel lists.
    # The saved selection belongs to preview; it never changes the execution set.
    return ([record.image_tensor for record in records], [record.mask_tensor for record in records])


def validate_collection_input(value, *, execution=True):
    """Validate saved state, optionally deferring runtime asset checks.

    ComfyUI validates inputs recursively even when a lazy branch will not execute. The
    compiler-facing mode therefore checks only the canonical state and cardinality; execution
    keeps the strict empty and file-existence checks.
    """
    try:
        state = parse_collection_state(value)
        if execution and not state.items:
            raise ImageCollectionValidationError("Add at least one image before running the collection.")
        if execution:
            for item in state.items:
                _verify_owned_input(item.image)
    except ImageCollectionValidationError as exc:
        return str(exc)
    return True


def input_digest(value):
    """Invalidate cached outputs when any referenced file changes or disappears."""
    state = parse_collection_state(value)
    digest = hashlib.sha256(canonical_state_json(state).encode("utf-8"))
    for item in state.items:
        path = _verify_owned_input(item.image)
        try:
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise ImageCollectionValidationError(f"Cannot read image: {item.image}") from exc
    return digest.hexdigest()


__all__ = [
    "CollectionItem",
    "CollectionState",
    "EMPTY_STATE_JSON",
    "ImageCollectionValidationError",
    "ImageRecord",
    "MAX_IMAGES",
    "STATE_VERSION",
    "canonical_state_json",
    "load_ordered_records",
    "parse_collection_state",
    "execute_utility_operation",
    "validate_collection_input",
    "input_digest",
]
