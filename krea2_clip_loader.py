"""Load Krea2 CLIP with instance-local GPU RMSNorm containment.

The returned object remains ComfyUI's native CLIP. Only its Qwen RMSNorm
instances receive bound forwards backed by independent CPU reference weights;
the native common_dit.rms_norm implementation still performs the math. This
contains the observed norm-weight corruption boundary. It does not claim to
remove an unknown writer elsewhere in the runtime.
"""
from __future__ import annotations

import threading
import types


_LOCK = threading.RLock()
_MARKER = "_matrix_krea2_norm_reference_state"
_GUARD_KEY = "matrix_krea2_encoder_patch_guard"


def _require_clean_patcher(patcher, model=None, hooks=None):
    if model is not None and patcher.model is not model:
        raise RuntimeError("Krea2 GPU CLIP patcher and encoder model do not match.")
    if getattr(getattr(patcher, "load_device", None), "type", None) != "cuda":
        raise RuntimeError("Krea2 GPU CLIP requires a CUDA encoder load device.")

    object_patches = getattr(patcher, "object_patches", None) or {}
    if object_patches:
        import torch

        if (
            set(object_patches) != {"manual_cast_dtype"}
            or object_patches["manual_cast_dtype"] is not torch.float32
        ):
            raise RuntimeError("Krea2 GPU CLIP refuses encoder object_patches.")

    for field in (
        "patches",
        "weight_wrapper_patches",
        "hook_patches",
        "hook_patches_backup",
        "cached_hook_patches",
        "wrappers",
        "injections",
    ):
        if getattr(patcher, field, None):
            raise RuntimeError(f"Krea2 GPU CLIP refuses encoder {field}.")
    if hooks is not None:
        raise RuntimeError("Krea2 GPU CLIP refuses encoder hooks.")
    for field in ("current_hooks", "forced_hooks"):
        if getattr(patcher, field, None) is not None:
            raise RuntimeError(f"Krea2 GPU CLIP refuses encoder {field}.")


def _make_norm_forward(reference, native_rms_norm):
    def forward(module, x):
        if getattr(getattr(x, "device", None), "type", None) != "cuda":
            raise RuntimeError("Krea2 GPU CLIP RMSNorm requires CUDA activations.")
        weight = reference + 1.0 if module.add else reference
        return native_rms_norm(x, weight, module.eps)

    return forward


def _install_norm_containment(clip):
    import torch
    from comfy.ldm import common_dit
    from comfy.text_encoders import llama

    with _LOCK:
        patcher = clip.patcher
        model = clip.cond_stage_model
        _require_clean_patcher(patcher, model=model)
        if not hasattr(model, "qwen3vl_4b"):
            raise RuntimeError("Krea2 GPU CLIP requires the Qwen3-VL 4B encoder.")

        if getattr(model, _MARKER, None) is not None:
            raise RuntimeError("Krea2 GPU CLIP norm containment was already installed.")

        references = {}
        modules = {}
        for name, module in model.named_modules():
            if not isinstance(module, llama.RMSNorm):
                continue
            if type(module) is not llama.RMSNorm or "forward" in module.__dict__:
                raise RuntimeError(f"Krea2 GPU CLIP refuses custom RMSNorm forward: {name}.")
            weight = module.weight
            if weight.device.type != "cpu" or weight.is_meta:
                raise RuntimeError(f"Krea2 GPU CLIP requires a fresh CPU RMSNorm source: {name}.")
            if weight.ndim != 1 or not weight.numel() or not weight.is_floating_point():
                raise RuntimeError(f"Krea2 GPU CLIP received an invalid RMSNorm source: {name}.")
            reference = weight.detach().to(device="cpu", copy=True).contiguous()
            if not bool(torch.isfinite(reference).all()):
                raise RuntimeError(f"Krea2 GPU CLIP received a nonfinite RMSNorm source: {name}.")
            if reference.data_ptr() == weight.data_ptr():
                raise RuntimeError(f"Krea2 GPU CLIP RMSNorm reference aliases its parameter: {name}.")
            references[name] = reference
            modules[name] = module
        if not references:
            raise RuntimeError("Krea2 GPU CLIP found no native llama.RMSNorm modules.")

        state = {"references": references, "forwards": {}}
        applied = []
        try:
            for name, module in modules.items():
                forward = _make_norm_forward(references[name], common_dit.rms_norm)
                module.forward = types.MethodType(forward, module)
                state["forwards"][name] = forward
                applied.append(module)
            setattr(model, _MARKER, state)
        except Exception:
            for module in applied:
                delattr(module, "forward")
            if getattr(model, _MARKER, None) is state:
                delattr(model, _MARKER)
            raise

        from comfy.patcher_extension import CallbacksMP

        def reject_encoder_patches(current_patcher, hooks):
            _require_clean_patcher(current_patcher, model=model, hooks=hooks)

        patcher.add_callback_with_key(
            CallbacksMP.ON_APPLY_HOOKS, _GUARD_KEY, reject_encoder_patches
        )


class MATRIX_Krea2CLIPLoader:
    RETURN_TYPES = ("CLIP",)
    RETURN_NAMES = ("clip",)
    FUNCTION = "load_clip"
    CATEGORY = "MATRIX LAB/Prompting"
    DESCRIPTION = "Load Krea2 text encoding on CUDA with instance-local RMSNorm containment. Diffusion loading is unchanged."

    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths

        return {"required": {"clip_name": (folder_paths.get_filename_list("text_encoders"),)}}

    def load_clip(self, clip_name):
        import torch
        import folder_paths
        import comfy.sd
        import comfy.model_management as management

        loader = comfy.sd.load_clip
        clip_type = getattr(comfy.sd.CLIPType, "KREA2", None)
        if clip_type is None:
            raise RuntimeError("This ComfyUI version does not support Krea2 text encoding.")
        device = management.get_torch_device()
        if getattr(device, "type", None) != "cuda":
            raise RuntimeError("Krea2 GPU CLIP requires a CUDA device selected by ComfyUI.")
        cpu = torch.device("cpu")
        path = folder_paths.get_full_path_or_raise("text_encoders", clip_name)
        clip = loader(
            ckpt_paths=[path],
            embedding_directory=folder_paths.get_folder_paths("embeddings"),
            clip_type=clip_type,
            model_options={"load_device": device, "offload_device": cpu, "initial_device": cpu},
        )
        patcher = clip.patcher
        if patcher.load_device != device:
            raise RuntimeError("Krea2 GPU CLIP could not preserve the selected CUDA load device.")
        if patcher.offload_device != cpu:
            raise RuntimeError("Krea2 GPU CLIP could not preserve CPU offload.")
        _install_norm_containment(clip)
        return (clip,)


NODE_CLASS_MAPPINGS = {"MATRIX_Krea2CLIPLoader": MATRIX_Krea2CLIPLoader}
NODE_DISPLAY_NAME_MAPPINGS = {"MATRIX_Krea2CLIPLoader": "MATRIX KREA2 CLIP LOADER"}
