"""Runtime enforcement for ComfyUI socket and widget declarations."""

from __future__ import annotations

from collections.abc import Mapping
from importlib import import_module
from typing import Any


class ContractValidationError(ValueError):
    """A declared socket or widget contract does not match its value."""


_SCALAR_TYPES = {
    "STRING": str,
    "BOOLEAN": bool,
    "INT": int,
    "FLOAT": float,
    "COMBO": str,
}

_ALIASES = {
    "NUMBER": "FLOAT,INT",
    "PRIMITIVE": "STRING,FLOAT,INT,BOOLEAN",
}

# ComfyUI runtime objects deliberately remain opaque at the shared contract seam. Their
# behavioral contracts belong to the operation that consumes them; the factory still rejects
# ``None`` so a missing connection cannot masquerade as a valid model/provider handle.
_OPAQUE_SOCKET_TYPES = frozenset(
    {
        "BBOX_DETECTOR",
        "CLIP",
        "CONDITIONING",
        "DETAILER_HOOK",
        "GUIDER",
        "MODEL",
        "NOISE",
        "SAM_MODEL",
        "SAMPLER",
        "SCHEDULER_FUNC",
        "SEGM_DETECTOR",
        "SEGS",
        "SIGMAS",
        "UPSCALE_MODEL",
        "VAE",
    }
)

_WIDGET_TYPES = frozenset({"STRING", "BOOLEAN", "INT", "FLOAT", "COMBO"})
_RESERVED_OPTION_OWNERS = {
    "min": frozenset({"INT", "FLOAT"}),
    "max": frozenset({"INT", "FLOAT"}),
    "step": frozenset({"INT", "FLOAT"}),
    "round": frozenset({"INT", "FLOAT"}),
    "multiline": frozenset({"STRING"}),
    "placeholder": frozenset({"STRING"}),
    "dynamicPrompts": frozenset({"STRING"}),
    "options": frozenset({"COMBO"}),
    "multiselect": frozenset({"COMBO"}),
    "multi_select": frozenset({"COMBO"}),
}


def _fail(socket_type: str, detail: str) -> None:
    raise ContractValidationError(f"{socket_type} contract violation: {detail}")


def _torch():
    try:
        return import_module("torch")
    except ImportError as exc:
        raise ContractValidationError(
            "tensor socket validation requires the ComfyUI torch runtime"
        ) from exc


def _validate_tensor(
    socket_type: str,
    value: Any,
    *,
    dimensions: int | tuple[int, ...],
    bounded: bool,
) -> None:
    torch = _torch()
    if not isinstance(value, torch.Tensor):
        _fail(socket_type, "expected a torch.Tensor")
    allowed = (dimensions,) if isinstance(dimensions, int) else tuple(dimensions)
    if value.ndim not in allowed:
        expected = " or ".join(str(item) for item in allowed)
        _fail(
            socket_type,
            f"expected {expected} dimensions, received shape {tuple(value.shape)}",
        )
    if any(size <= 0 for size in value.shape):
        _fail(socket_type, f"every dimension must be non-empty: {tuple(value.shape)}")
    if not value.dtype.is_floating_point:
        _fail(socket_type, f"expected a floating dtype, received {value.dtype}")
    if bounded:
        if not bool(torch.isfinite(value).all().item()):
            _fail(socket_type, "all values must be finite")
        minimum = value.amin().item()
        maximum = value.amax().item()
        if minimum < 0.0 or maximum > 1.0:
            _fail(
                socket_type,
                f"values must be in 0..1, received range {minimum}..{maximum}",
            )


def _validate_scalar(socket_type: str, value: Any) -> None:
    expected = _SCALAR_TYPES[socket_type]
    if type(value) is not expected:
        _fail(
            socket_type,
            f"expected exact {expected.__name__}, received {type(value).__name__}",
        )


def _validate_single_socket(socket_type: str, value: Any) -> None:
    if socket_type in _SCALAR_TYPES:
        _validate_scalar(socket_type, value)
        return

    if socket_type == "IMAGE":
        _validate_tensor(socket_type, value, dimensions=4, bounded=True)
        return

    if socket_type == "MASK":
        _validate_tensor(socket_type, value, dimensions=3, bounded=True)
        return

    if socket_type == "LATENT":
        if not isinstance(value, dict):
            _fail(socket_type, "expected a dictionary containing 'samples'")
        if "samples" not in value:
            _fail(socket_type, "missing required 'samples' entry")
        # Image latents are [B,C,H,W]; video and flow families (Wan VAE behind Krea 2) carry a
        # temporal axis: [B,C,T,H,W]. Both are native ComfyUI LATENT payloads.
        _validate_tensor(
            "LATENT.samples",
            value["samples"],
            dimensions=(4, 5),
            bounded=False,
        )
        return

    if socket_type == "VIDEO":
        missing = [
            method
            for method in ("get_dimensions", "save_to")
            if not callable(getattr(value, method, None))
        ]
        if missing:
            _fail(
                socket_type,
                f"expected the VideoInput consumer protocol; missing {', '.join(missing)}",
            )
        return

    if socket_type == "BBOX":
        # KJNodes convention: a list of (x0, y0, x1, y1) integer boxes, exclusive right/bottom.
        if not isinstance(value, (list, tuple)):
            _fail(socket_type, "expected a list of (x0, y0, x1, y1) boxes")
        for index, box in enumerate(value):
            if not isinstance(box, (list, tuple)) or len(box) != 4:
                _fail(socket_type, f"box {index} must hold exactly four numbers")
            if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in box):
                _fail(socket_type, f"box {index} must hold numbers only")
            x0, y0, x1, y1 = box
            if not (x1 > x0 and y1 > y0) or min(box) < 0:
                _fail(socket_type, f"box {index} must be non-negative with x1 > x0 and y1 > y0")
        return

    if socket_type == "MATRIX_REFERENCE_SET":
        tensors = getattr(value, "tensors", None)
        if type(tensors) is not tuple or not tensors:
            _fail(
                socket_type,
                "expected a non-empty immutable tuple of IMAGE tensors",
            )
        if getattr(value, "batch_policy", None) != "slot-then-frame":
            _fail(socket_type, "expected slot-then-frame batch policy")
        for tensor in tensors:
            _validate_single_socket("IMAGE", tensor)
        return

    if socket_type in _OPAQUE_SOCKET_TYPES:
        if value is None:
            _fail(socket_type, "expected a connected non-None runtime object")
        return

    _fail(
        socket_type,
        "no executable payload convention is defined for this label",
    )


def validate_socket_value(socket_type: str, value: Any) -> Any:
    """Validate one produced value against a declared socket type.

    The original value is returned for convenient boundary checks. It is never
    coerced or copied.
    """

    if not isinstance(socket_type, str) or not socket_type:
        raise ContractValidationError("socket type must be a non-empty string")

    declared = _ALIASES.get(socket_type, socket_type)
    if declared == "*":
        return value

    members = declared.split(",")
    if len(members) == 1:
        _validate_single_socket(members[0], value)
        return value

    failures = []
    for member in members:
        try:
            _validate_single_socket(member, value)
            return value
        except ContractValidationError as exc:
            failures.append(str(exc))
    raise ContractValidationError(
        f"{socket_type} contract violation: value matched no union member "
        f"({'; '.join(failures)})"
    )


def validate_widget_options(
    widget_type: str,
    options: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Reject reserved option keys that do not belong to the widget type."""

    if widget_type not in _WIDGET_TYPES:
        raise ContractValidationError(
            f"{widget_type!r} is not a supported scalar widget type"
        )
    if not isinstance(options, Mapping):
        raise ContractValidationError("widget options must be a mapping")

    for key in options:
        if not isinstance(key, str):
            raise ContractValidationError("widget option keys must be strings")
        owners = _RESERVED_OPTION_OWNERS.get(key)
        if owners is not None and widget_type not in owners:
            allowed = ", ".join(sorted(owners))
            raise ContractValidationError(
                f"{key!r} is not legal for {widget_type}; allowed for {allowed}"
            )
    return options
