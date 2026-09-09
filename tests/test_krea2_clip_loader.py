"""Focused offline tests for the Krea2 GPU CLIP containment loader."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

import torch


SOURCE = Path(__file__).resolve().parents[1] / "krea2_clip_loader.py"
SPEC = importlib.util.spec_from_file_location("matrix_krea2_clip_loader_test", SOURCE)
LOADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOADER)


class NativeRMSNorm(torch.nn.Module):
    def __init__(self, weight=(2.0, 3.0), eps=0.25, add=False):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.tensor(weight))
        self.eps = eps
        self.add = add

    def forward(self, x):
        raise AssertionError("native module forward should be replaced per instance")


class Encoder(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.qwen3vl_4b = object()
        self.norm = NativeRMSNorm(add=True)


class Patcher:
    def __init__(self, model):
        self.model = model
        self.load_device = torch.device("cuda")
        self.offload_device = torch.device("cpu")
        self.patches = {}
        self.object_patches = {"manual_cast_dtype": torch.float32}
        self.weight_wrapper_patches = {}
        self.hook_patches = {}
        self.hook_patches_backup = {}
        self.cached_hook_patches = {}
        self.wrappers = {}
        self.injections = {}
        self.current_hooks = None
        self.forced_hooks = None
        self.callbacks = {}

    def is_dynamic(self):
        return True

    def add_callback_with_key(self, call_type, key, callback):
        self.callbacks.setdefault(call_type, {}).setdefault(key, []).append(callback)

    def clone(self):
        clone = Patcher(self.model)
        clone.callbacks = {
            call_type: {key: callbacks.copy() for key, callbacks in keyed.items()}
            for call_type, keyed in self.callbacks.items()
        }
        return clone


def fake_comfy_modules(native_rms_norm):
    calls = []

    def rms_norm(x, weight, eps):
        calls.append((x, weight.clone(), eps))
        return weight.clone()

    comfy = types.ModuleType("comfy")
    comfy.__path__ = []
    ldm = types.ModuleType("comfy.ldm")
    ldm.__path__ = []
    common_dit = types.ModuleType("comfy.ldm.common_dit")
    common_dit.rms_norm = rms_norm
    text_encoders = types.ModuleType("comfy.text_encoders")
    text_encoders.__path__ = []
    llama = types.ModuleType("comfy.text_encoders.llama")
    llama.RMSNorm = native_rms_norm
    extension = types.ModuleType("comfy.patcher_extension")
    extension.CallbacksMP = types.SimpleNamespace(ON_APPLY_HOOKS="on_apply_hooks")
    comfy.ldm = ldm
    comfy.text_encoders = text_encoders
    ldm.common_dit = common_dit
    text_encoders.llama = llama
    return {
        "comfy": comfy,
        "comfy.ldm": ldm,
        "comfy.ldm.common_dit": common_dit,
        "comfy.text_encoders": text_encoders,
        "comfy.text_encoders.llama": llama,
        "comfy.patcher_extension": extension,
    }, calls


class Krea2ClipLoaderTests(unittest.TestCase):
    def install(self):
        model = Encoder()
        clip = types.SimpleNamespace(cond_stage_model=model, patcher=Patcher(model))
        modules, calls = fake_comfy_modules(NativeRMSNorm)
        with patch.dict(sys.modules, modules):
            LOADER._install_norm_containment(clip)
        return clip, calls

    def test_reference_is_independent_and_preserves_native_norm_add_and_eps(self):
        native_forward = NativeRMSNorm.forward
        clip, calls = self.install()
        state = getattr(clip.cond_stage_model, LOADER._MARKER)
        reference = state["references"]["norm"]
        self.assertEqual(reference.device.type, "cpu")
        self.assertNotEqual(reference.data_ptr(), clip.cond_stage_model.norm.weight.data_ptr())
        self.assertIs(NativeRMSNorm.forward, native_forward)
        self.assertNotIn("__class__", clip.cond_stage_model.norm.__dict__)
        with torch.no_grad():
            clip.cond_stage_model.norm.weight.fill_(99.0)

        fake_cuda_activation = types.SimpleNamespace(device=types.SimpleNamespace(type="cuda"))
        result = clip.cond_stage_model.norm(fake_cuda_activation)
        self.assertTrue(torch.equal(result, torch.tensor([3.0, 4.0])))
        self.assertTrue(torch.equal(calls[0][1], torch.tensor([3.0, 4.0])))
        self.assertEqual(calls[0][2], 0.25)

    def test_norm_forward_refuses_non_cuda_activation(self):
        clip, _ = self.install()
        with self.assertRaisesRegex(RuntimeError, "requires CUDA activations"):
            clip.cond_stage_model.norm(torch.ones(2))

    def test_guard_is_copied_to_clone_and_rejects_each_patch_surface(self):
        clip, _ = self.install()
        clone = clip.patcher.clone()
        guard = clone.callbacks["on_apply_hooks"][LOADER._GUARD_KEY][0]
        guard(clone, None)
        cases = (
            ("patches", {"layer": [object()]}),
            ("weight_wrapper_patches", {"layer": object()}),
            ("hook_patches", {object(): {"layer": [object()]}}),
            ("hook_patches_backup", {object(): {"layer": [object()]}}),
            ("cached_hook_patches", {object(): {"layer": [object()]}}),
            ("wrappers", {"apply_model": {None: [object()]}}),
            ("injections", {"bypass_lora": [object()]}),
            ("current_hooks", object()),
            ("forced_hooks", object()),
        )
        for field, value in cases:
            candidate = clone.clone()
            setattr(candidate, field, value)
            with self.subTest(field=field), self.assertRaisesRegex(RuntimeError, "refuses encoder"):
                guard(candidate, None)
        with self.assertRaisesRegex(RuntimeError, "refuses encoder hooks"):
            guard(clone, object())

    def test_guard_accepts_native_manual_cast_and_rejects_changed_or_extra_object_patch(self):
        clip, _ = self.install()
        guard = clip.patcher.callbacks["on_apply_hooks"][LOADER._GUARD_KEY][0]
        guard(clip.patcher, None)

        clip.patcher.object_patches = {"manual_cast_dtype": torch.bfloat16}
        with self.assertRaisesRegex(RuntimeError, "refuses encoder object_patches"):
            guard(clip.patcher, None)

        clip.patcher.object_patches = {
            "manual_cast_dtype": torch.float32,
            "unexpected": object(),
        }
        with self.assertRaisesRegex(RuntimeError, "refuses encoder object_patches"):
            guard(clip.patcher, None)

    def test_loader_returns_original_clip_and_requests_cpu_initial_state(self):
        model = Encoder()
        clip = types.SimpleNamespace(cond_stage_model=model, patcher=Patcher(model))
        captured = {}

        def native_load_clip(
            ckpt_paths, embedding_directory, clip_type, model_options, disable_dynamic=False
        ):
            captured.update(locals())
            return clip

        comfy = types.ModuleType("comfy")
        comfy.__path__ = []
        sd = types.ModuleType("comfy.sd")
        sd.load_clip = native_load_clip
        sd.CLIPType = types.SimpleNamespace(KREA2="krea2")
        management = types.ModuleType("comfy.model_management")
        management.get_torch_device = lambda: torch.device("cuda")
        comfy.sd = sd
        comfy.model_management = management
        folder_paths = types.ModuleType("folder_paths")
        folder_paths.get_full_path_or_raise = lambda kind, name: f"/models/{name}"
        folder_paths.get_folder_paths = lambda kind: ["/embeddings"]
        norm_modules, _ = fake_comfy_modules(NativeRMSNorm)
        modules = {
            **norm_modules,
            "comfy": comfy,
            "comfy.sd": sd,
            "comfy.model_management": management,
            "folder_paths": folder_paths,
        }

        with patch.dict(sys.modules, modules):
            result = LOADER.MATRIX_Krea2CLIPLoader().load_clip("qwen.safetensors")

        self.assertIs(result[0], clip)
        self.assertFalse(captured["disable_dynamic"])
        self.assertEqual(captured["clip_type"], "krea2")
        options = captured["model_options"]
        self.assertEqual(options["load_device"].type, "cuda")
        self.assertEqual(options["offload_device"].type, "cpu")
        self.assertEqual(options["initial_device"].type, "cpu")

    def test_loader_requires_comfy_cuda_selection(self):
        comfy = types.ModuleType("comfy")
        comfy.__path__ = []
        sd = types.ModuleType("comfy.sd")
        sd.load_clip = lambda ckpt_paths, embedding_directory, clip_type, model_options: None
        sd.CLIPType = types.SimpleNamespace(KREA2="krea2")
        management = types.ModuleType("comfy.model_management")
        management.get_torch_device = lambda: torch.device("cpu")
        comfy.sd = sd
        comfy.model_management = management
        folder_paths = types.ModuleType("folder_paths")
        folder_paths.get_full_path_or_raise = lambda kind, name: "/unused"
        folder_paths.get_folder_paths = lambda kind: []
        with patch.dict(
            sys.modules,
            {
                "comfy": comfy,
                "comfy.sd": sd,
                "comfy.model_management": management,
                "folder_paths": folder_paths,
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "requires a CUDA device"):
                LOADER.MATRIX_Krea2CLIPLoader().load_clip("qwen.safetensors")


if __name__ == "__main__":
    unittest.main()
