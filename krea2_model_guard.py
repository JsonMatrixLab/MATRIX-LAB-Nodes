"""Static GPU Krea2 loading with instance-local norm/modulation containment.

The node replaces a dynamic MODEL with a cached native static CUDA delegate.
Already static MODEL inputs are reused. install() preserves its input identity.

Independent CPU parameter references contain observed resident corruption. This
does not repair the unknown writer or certify arbitrary model patches.
"""
from __future__ import annotations

import logging
import threading
import types


_LOCK = threading.RLock()
_MARKER = "_matrix_krea2_diffusion_norm_references"
_CALLBACK_KEY = "matrix_krea2_diffusion_norm_guard"
_STATE_SCHEMA = "norm-and-modulation.v1"


def _check_patcher(patcher, model, scale_keys):
    if patcher.model is not model:
        raise RuntimeError("Krea2 model guard requires clones sharing the original model.")
    if getattr(getattr(patcher, "load_device", None), "type", None) != "cuda":
        raise RuntimeError("Krea2 model guard requires a CUDA load device.")
    for field in ("patches", "weight_wrapper_patches", "object_patches"):
        entries = getattr(patcher, field, None) or {}
        if not isinstance(entries, dict):
            raise RuntimeError(f"Krea2 model guard cannot inspect {field}.")
        for key in entries:
            if not isinstance(key, str):
                raise RuntimeError(f"Krea2 model guard refuses unknown {field} key type.")
            targets_scale = key in scale_keys
            if field == "object_patches":
                targets_scale |= any(name.startswith(key + ".") for name in scale_keys)
                targets_scale |= any(key == name.rsplit(".", 1)[0] + ".forward" for name in scale_keys)
            if targets_scale:
                raise RuntimeError(f"Krea2 model guard refuses a protected parameter patch: {key}.")
    # Scheduled hooks can install weights after pre_run; their target/lifetime
    # semantics are not covered by the independent reference contract.
    for field in ("hook_patches", "hook_patches_backup", "cached_hook_patches",
                  "current_hooks", "forced_hooks"):
        if getattr(patcher, field, None):
            raise RuntimeError(f"Krea2 model guard refuses unknown hook semantics: {field}.")
    transformer = getattr(patcher, "model_options", {}).get("transformer_options", {})
    if transformer.get("hooks"):
        raise RuntimeError("Krea2 model guard refuses transformer hooks.")


def _make_forward(reference, cast_to, rms_norm, float32):
    def forward(module, x):
        if getattr(getattr(x, "device", None), "type", None) != "cuda":
            raise RuntimeError("Krea2 model guard RMSNorm requires CUDA activations.")
        # Exact native Krea2 convention: FP32 cast before adding the unit offset.
        weight = cast_to(reference, dtype=float32, device=x.device) + 1.0
        return rms_norm(x.float(), (x.shape[-1],), weight=weight, eps=module.eps).to(x.dtype)
    return forward


def _make_modulation_forward(reference, cast_to, simple):
    def forward(module, vec):
        if getattr(getattr(vec, "device", None), "type", None) != "cuda":
            raise RuntimeError("Krea2 model guard modulation requires CUDA activations.")
        weight = cast_to(reference, dtype=vec.dtype, device=vec.device)
        if simple:
            out = vec + weight.unsqueeze(0)
            scale, shift = out.chunk(2, dim=1)
            return scale, shift
        out = vec + weight
        return out.chunk(6, dim=-1)
    return forward


def _ensure_callback(patcher, callback_type, callback):
    getter = getattr(patcher, "get_callbacks", None)
    if not callable(getter):
        raise RuntimeError("Krea2 model guard requires native keyed callback inspection.")
    existing = getter(callback_type, _CALLBACK_KEY)
    if existing:
        if len(existing) != 1 or existing[0] is not callback:
            raise RuntimeError("Krea2 model guard callback was changed.")
    else:
        patcher.add_callback_with_key(callback_type, _CALLBACK_KEY, callback)


def _reuse(state, model_patcher, model, native_specs, torch, callback_type):
    if (not isinstance(state, dict) or state.get("schema") != _STATE_SCHEMA or state.get("model") is not model
            or getattr(model, _MARKER, None) is not state):
        raise RuntimeError("Krea2 model guard has a stale reference marker.")
    try:
        modules = {name: module for name, module in model.named_modules()
                   if isinstance(module, tuple(native_specs))}
        expected = state["modules"]
        if modules.keys() != expected.keys():
            raise RuntimeError("Krea2 model guard norm inventory changed.")
        references = state["references"]
        if references.keys() != modules.keys():
            raise RuntimeError("Krea2 model guard reference inventory changed.")
        parameter_names = {name: native_specs[type(module)][0] for name, module in modules.items()}
        if state["parameter_names"] != parameter_names:
            raise RuntimeError("Krea2 model guard protected parameter mapping changed.")
        scale_keys = frozenset((name + "." if name else "") + param for name, param in parameter_names.items())
        if state["scale_keys"] != scale_keys:
            raise RuntimeError("Krea2 model guard scale inventory changed.")
        for name, module in modules.items():
            reference = references[name]
            if (module is not expected[name] or type(module) is not state["classes"][name]
                    or module.forward is not state["forwards"][name]
                    or reference is not state["reference_identities"][name]):
                raise RuntimeError("Krea2 model guard module/forward/reference identity changed.")
            parameter = getattr(module, parameter_names[name])
            if (reference.device.type != "cpu" or reference.is_meta
                    or tuple(reference.shape) != tuple(parameter.shape)
                    or reference.data_ptr() == parameter.data_ptr()
                    or not bool(torch.isfinite(reference).all())
                    or reference._version != state["reference_versions"][name]):
                raise RuntimeError("Krea2 model guard reference integrity changed.")
        _check_patcher(model_patcher, model, scale_keys)
        _ensure_callback(model_patcher, callback_type, state["callback"])
    except (KeyError, AttributeError, TypeError) as exc:
        raise RuntimeError("Krea2 model guard has an invalid reference marker.") from exc
    return model_patcher


def install(model_patcher):
    import torch
    import torch.nn.functional as functional
    from comfy.ldm.krea2.model import RMSNorm, SimpleModulation, DoubleSharedModulation
    from comfy.model_management import cast_to
    from comfy.patcher_extension import CallbacksMP

    with _LOCK:
        model = model_patcher.model
        if not callable(getattr(model_patcher, "add_callback_with_key", None)):
            raise RuntimeError("Krea2 model guard requires native patcher callbacks.")
        callback_type = CallbacksMP.ON_PRE_RUN
        native_specs = {RMSNorm: ("scale", 1), SimpleModulation: ("lin", 2), DoubleSharedModulation: ("lin", 1)}
        if hasattr(model, _MARKER):
            return _reuse(getattr(model, _MARKER), model_patcher, model, native_specs, torch, callback_type)
        modules = {}
        references = {}
        for name, module in model.named_modules():
            if not isinstance(module, tuple(native_specs)):
                continue
            if type(module) not in native_specs or "forward" in module.__dict__:
                raise RuntimeError(f"Krea2 model guard refuses a custom protected forward: {name}.")
            parameter_name, ndim = native_specs[type(module)]
            scale = getattr(module, parameter_name)
            if scale.device.type != "cpu" or scale.is_meta:
                raise RuntimeError(f"Krea2 model guard requires fresh CPU protected parameters: {name}.")
            if (scale.ndim != ndim or not scale.numel() or not scale.is_floating_point()
                    or (type(module) is SimpleModulation and scale.shape[0] != 2)
                    or (type(module) is DoubleSharedModulation and scale.numel() % 6)):
                raise RuntimeError(f"Krea2 model guard received an invalid protected parameter: {name}.")
            # Comfy executes nodes in inference_mode; ordinary tensors retain a
            # mutation counter so a later cache re-entry can verify integrity.
            with torch.inference_mode(False):
                reference = scale.detach().to(device="cpu", copy=True).contiguous()
            if not bool(torch.isfinite(reference).all()):
                raise RuntimeError(f"Krea2 model guard received a nonfinite protected parameter: {name}.")
            if reference.data_ptr() == scale.data_ptr():
                raise RuntimeError(f"Krea2 model guard reference aliases scale: {name}.")
            modules[name] = module
            references[name] = reference
        if not modules:
            raise RuntimeError("Krea2 model guard found no native Krea2 RMSNorm modules.")
        parameter_names = {name: native_specs[type(module)][0] for name, module in modules.items()}
        scale_keys = frozenset((name + "." if name else "") + param for name, param in parameter_names.items())
        _check_patcher(model_patcher, model, scale_keys)

        def pre_run(current_patcher):
            _reuse(state, current_patcher, model, native_specs, torch, callback_type)

        # Plain dict storage is deliberately outside registered parameters/buffers.
        state = {"schema": _STATE_SCHEMA, "model": model, "modules": modules, "references": references,
                 "parameter_names": parameter_names, "classes": {name: type(module) for name, module in modules.items()},
                 "reference_identities": references.copy(),
                 "reference_versions": {name: value._version for name, value in references.items()},
                 "forwards": {}, "scale_keys": scale_keys, "callback": pre_run}
        _ensure_callback(model_patcher, callback_type, pre_run)
        for name, module in modules.items():
            forward = (_make_forward(references[name], cast_to, functional.rms_norm, torch.float32)
                       if type(module) is RMSNorm else
                       _make_modulation_forward(references[name], cast_to, type(module) is SimpleModulation))
            module.forward = types.MethodType(
                forward, module
            )
            state["forwards"][name] = module.forward
        setattr(model, _MARKER, state)
        size = sum(value.numel() * value.element_size() for value in references.values())
        logging.getLogger("MATRIX.Krea2ModelGuard").info(
            "Installed native GPU norm/modulation containment: %d CPU references, %d bytes", len(references), size
        )
    return model_patcher



_STATIC_CACHE = "_matrix_krea2_static_guard_delegate"


def _static_guard(model_patcher):
    """One native static delegate for each unpatched loader patcher.

    Cache ownership follows the source patcher, not the node instance or a global
    table. Native parent links can form a collectable cycle, but no global root
    retains unused models. Never reload a model whose forwards are guarded.
    """
    with _LOCK:
        if getattr(getattr(model_patcher, "load_device", None), "type", None) != "cuda":
            raise RuntimeError("Krea2 model guard requires a CUDA load device.")
        dynamic = getattr(model_patcher, "is_dynamic", None)
        if not callable(dynamic):
            raise RuntimeError("Krea2 static guard requires native patcher dynamic inspection.")
        if not dynamic():
            return install(model_patcher)
        if hasattr(model_patcher.model, _MARKER):
            raise RuntimeError("Krea2 static guard refuses an already guarded dynamic model.")
        if getattr(model_patcher, "patches", None):
            raise RuntimeError("Connect Krea2 static guard before diffusion LoRAs.")
        _check_patcher(model_patcher, model_patcher.model, frozenset())
        if hasattr(model_patcher, _STATIC_CACHE):
            state = getattr(model_patcher, _STATIC_CACHE)
            if (not isinstance(state, dict) or state.get("schema") != "static-delegate.v1"
                    or state.get("source_model") is not model_patcher.model):
                raise RuntimeError("Krea2 static guard has a stale delegate cache.")
            delegate = state.get("delegate")
            if (delegate is None or delegate.model is not state.get("delegate_model")
                    or delegate.is_dynamic()
                    or getattr(delegate.model, _MARKER, None) is not state.get("guard_state")):
                raise RuntimeError("Krea2 static guard delegate identity changed.")
            for field, entries in state["source_entries"].items():
                current = getattr(model_patcher, field, None) or {}
                if current.keys() != entries.keys() or any(current[k] is not v for k, v in entries.items()):
                    raise RuntimeError("Krea2 static guard source patches changed.")
            return install(delegate)
        # Invoke the concrete clone override: INT8 restores its own mixin here.
        delegate = model_patcher.clone(disable_dynamic=True)
        if (delegate is model_patcher or delegate.model is model_patcher.model
                or delegate.is_dynamic()):
            raise RuntimeError("Krea2 static guard requires an independent native static clone.")
        if getattr(getattr(delegate, "load_device", None), "type", None) != "cuda":
            raise RuntimeError("Krea2 static guard clone requires a CUDA load device.")
        if hasattr(delegate.model, _MARKER):
            raise RuntimeError("Krea2 static guard refuses a previously guarded delegate.")
        delegate = install(delegate)
        setattr(model_patcher, _STATIC_CACHE, {
            "schema": "static-delegate.v1", "source_model": model_patcher.model,
            "delegate": delegate, "delegate_model": delegate.model,
            "guard_state": getattr(delegate.model, _MARKER),
            "source_entries": {field: (getattr(model_patcher, field, None) or {}).copy()
                               for field in ("object_patches", "weight_wrapper_patches")},
        })
        return delegate


class MATRIX_Krea2ModelGuard:
    RETURN_TYPES = ("MODEL",)
    RETURN_NAMES = ("model",)
    FUNCTION = "guard"
    CATEGORY = "MATRIX LAB/Sampling & Detail"
    DESCRIPTION = "Load and reuse a native static GPU model with protected Krea2 norm and modulation parameters. Connect before diffusion LoRAs."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": ("MODEL",)}}

    def guard(self, model):
        return (_static_guard(model),)


NODE_CLASS_MAPPINGS = {"MATRIX_Krea2ModelGuard": MATRIX_Krea2ModelGuard}
NODE_DISPLAY_NAME_MAPPINGS = {"MATRIX_Krea2ModelGuard": "MATRIX KREA2 MODEL GUARD"}
