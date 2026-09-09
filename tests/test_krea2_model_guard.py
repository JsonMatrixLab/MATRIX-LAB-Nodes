"""Offline model-guard contracts using native-shaped patcher/module doubles."""
import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

import torch
import torch.nn.functional as functional


spec = importlib.util.spec_from_file_location(
    "krea2_model_guard_test", Path(__file__).resolve().parents[1] / "krea2_model_guard.py"
)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class RMSNorm(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.scale = torch.nn.Parameter(torch.tensor([0.125, -0.25, 0.5], dtype=torch.bfloat16))
        self.eps = 1e-5

    def forward(self, x):
        return functional.rms_norm(x.float(), (x.shape[-1],), self.scale.float() + 1, self.eps).to(x.dtype)


class SimpleModulation(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.lin = torch.nn.Parameter(torch.arange(6, dtype=torch.bfloat16).reshape(2, 3) / 8)

    def forward(self, vec):
        out = vec + self.lin.to(dtype=vec.dtype, device=vec.device).unsqueeze(0)
        scale, shift = out.chunk(2, dim=1)
        return scale, shift


class DoubleSharedModulation(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.lin = torch.nn.Parameter(torch.arange(18, dtype=torch.bfloat16) / 8)

    def forward(self, vec):
        out = vec + self.lin.to(dtype=vec.dtype, device=vec.device)
        return out.chunk(6, dim=-1)


class Patcher:
    def __init__(self):
        self.model = torch.nn.Module()
        self.model.diffusion_model = torch.nn.Module()
        self.model.diffusion_model.norm = RMSNorm()
        self.model.diffusion_model.simple = SimpleModulation()
        self.model.diffusion_model.shared = DoubleSharedModulation()
        self.load_device = torch.device("cuda")
        self.patches = {}
        self.object_patches = {}
        self.weight_wrapper_patches = {}
        self.wrappers = {"custom_int8_forward": object()}
        self.callbacks = {}

    def add_callback_with_key(self, kind, key, callback):
        self.callbacks.setdefault(kind, {}).setdefault(key, []).append(callback)

    def get_callbacks(self, kind, key):
        return self.callbacks.get(kind, {}).get(key, [])

    def is_dynamic(self):
        return False

    def clone(self):
        result = copy.copy(self)
        result.patches = self.patches.copy()
        result.callbacks = {k: {n: v.copy() for n, v in d.items()} for k, d in self.callbacks.items()}
        return result

    def pre_run(self):
        for callbacks in self.callbacks.get("pre_run", {}).values():
            for callback in callbacks:
                callback(self)


class CUDAInput:
    """Claim CUDA at the checked seam while doing the arithmetic offline on CPU."""
    def __init__(self, value):
        self.value = value
        self.device = torch.device("cuda")
        self.dtype = value.dtype
        self.shape = value.shape

    def float(self):
        return self.value.float()

    def __add__(self, other):
        return self.value + other


class ModelGuardTests(unittest.TestCase):
    def setUp(self):
        self.casts = []

        def cast_to(value, dtype, device):
            self.casts.append((value, dtype, device))
            return value.to(dtype=dtype)

        self.modules = {
            "comfy.ldm.krea2.model": types.SimpleNamespace(
                RMSNorm=RMSNorm, SimpleModulation=SimpleModulation, DoubleSharedModulation=DoubleSharedModulation),
            "comfy.model_management": types.SimpleNamespace(cast_to=cast_to),
            "comfy.patcher_extension": types.SimpleNamespace(CallbacksMP=types.SimpleNamespace(ON_PRE_RUN="pre_run")),
        }
        self.context = patch.dict(sys.modules, self.modules)
        self.context.start()
        self.addCleanup(self.context.stop)
        self.patcher = Patcher()

    def test_same_model_independent_unregistered_references_and_cached_reinvoke(self):
        model = self.patcher.model
        before = set(model.state_dict())
        self.assertIs(guard.MATRIX_Krea2ModelGuard().guard(self.patcher)[0], self.patcher)
        reference = getattr(model, guard._MARKER)["references"]["diffusion_model.norm"]
        scale = model.diffusion_model.norm.scale
        self.assertNotEqual(reference.data_ptr(), scale.data_ptr())
        self.assertEqual(reference.device.type, "cpu")
        self.assertEqual(set(model.state_dict()), before)
        with torch.no_grad():
            scale.fill_(float("nan"))
        self.assertTrue(torch.isfinite(reference).all())
        self.assertIs(guard.install(self.patcher), self.patcher)
        self.assertIs(getattr(model, guard._MARKER)["references"]["diffusion_model.norm"], reference)
        self.assertEqual(len(self.patcher.get_callbacks("pre_run", guard._CALLBACK_KEY)), 1)
        clone = self.patcher.clone()
        self.assertIs(guard.install(clone), clone)
        self.assertEqual(len(clone.get_callbacks("pre_run", guard._CALLBACK_KEY)), 1)
        clone.callbacks = {}
        self.assertIs(guard.install(clone), clone)
        self.assertEqual(len(clone.get_callbacks("pre_run", guard._CALLBACK_KEY)), 1)
        self.assertTrue(torch.isfinite(model.diffusion_model.norm(CUDAInput(torch.ones(1, 3)))).all())

    def test_reinvoke_rejects_tampered_marker_references_forward_and_inventory(self):
        for mutation in ("marker", "reference", "forward", "inventory", "reference_value"):
            with self.subTest(mutation=mutation):
                patcher = Patcher()
                guard.install(patcher)
                state = getattr(patcher.model, guard._MARKER)
                if mutation == "marker":
                    setattr(patcher.model, guard._MARKER, {})
                elif mutation == "reference":
                    state["references"]["diffusion_model.norm"] = torch.zeros(3)
                elif mutation == "reference_value":
                    state["references"]["diffusion_model.norm"].add_(1)
                elif mutation == "forward":
                    patcher.model.diffusion_model.norm.forward = lambda x: x
                else:
                    patcher.model.diffusion_model.extra = RMSNorm()
                with self.assertRaises(RuntimeError):
                    guard.install(patcher)

    def test_exact_native_formula_survives_scale_corruption(self):
        norm = self.patcher.model.diffusion_model.norm
        value = torch.tensor([[1.0, 3.0, -2.0]], dtype=torch.bfloat16)
        expected = norm(value)
        guard.install(self.patcher)
        with torch.no_grad():
            norm.scale.fill_(float("nan"))
        actual = norm(CUDAInput(value))
        self.assertTrue(torch.equal(actual, expected))
        self.assertEqual(self.casts[0][1:], (torch.float32, torch.device("cuda")))
        without_offset = functional.rms_norm(value.float(), (3,), self.casts[0][0].float(), norm.eps).to(value.dtype)
        self.assertFalse(torch.equal(actual, without_offset))

    def test_clone_pre_run_accepts_linear_lora_and_rejects_norm_scale(self):
        guard.install(self.patcher)
        clone = self.patcher.clone()
        clone.patches["diffusion_model.blocks.0.attn.wq.weight"] = [object()]
        clone.pre_run()
        clone.patches["diffusion_model.norm.scale"] = [object()]
        with self.assertRaisesRegex(RuntimeError, "protected parameter patch"):
            clone.pre_run()
        self.patcher.pre_run()

    def test_unknown_keys_hooks_and_ancestor_replacements_are_refused(self):
        for field, value in [
            ("patches", {(1, 2): []}),
            ("object_patches", {"diffusion_model": object()}),
            ("weight_wrapper_patches", {"diffusion_model.norm.scale": object()}),
            ("hook_patches", {object(): {}}),
        ]:
            with self.subTest(field=field):
                patcher = Patcher()
                setattr(patcher, field, value)
                with self.assertRaises(RuntimeError):
                    guard.install(patcher)
                self.assertNotIn("forward", patcher.model.diffusion_model.norm.__dict__)

    def test_cuda_load_and_activation_requirements(self):
        self.patcher.load_device = torch.device("cpu")
        with self.assertRaisesRegex(RuntimeError, "CUDA load"):
            guard.install(self.patcher)
        self.patcher.load_device = torch.device("cuda")
        guard.install(self.patcher)
        with self.assertRaisesRegex(RuntimeError, "CUDA activations"):
            self.patcher.model.diffusion_model.norm(torch.ones(1, 3))

    def test_nonfinite_and_non_cpu_scales_refused_before_mutation(self):
        for value in [torch.tensor([float("nan")]), torch.empty(3, device="meta")]:
            patcher = Patcher()
            patcher.model.diffusion_model.norm.scale = torch.nn.Parameter(value)
            with self.assertRaises(RuntimeError):
                guard.install(patcher)
            self.assertFalse(patcher.callbacks)
            self.assertNotIn("forward", patcher.model.diffusion_model.norm.__dict__)

    def test_instance_forward_does_not_modify_other_models(self):
        other = Patcher()
        guard.install(self.patcher)
        self.assertNotIn("forward", other.model.diffusion_model.norm.__dict__)
        self.assertTrue(torch.isfinite(other.model.diffusion_model.norm(torch.ones(1, 3))).all())

    def test_install_and_reinvoke_under_comfy_inference_mode(self):
        with torch.inference_mode():
            self.assertIs(guard.install(self.patcher), self.patcher)
            self.assertIs(guard.install(self.patcher), self.patcher)

    def test_both_native_modulation_formulas_survive_resident_corruption(self):
        model = self.patcher.model.diffusion_model
        simple_input = torch.arange(6, dtype=torch.bfloat16).reshape(1, 2, 3)
        double_input = torch.arange(18, dtype=torch.bfloat16).reshape(1, 18)
        expected_simple = model.simple(simple_input)
        expected_double = model.shared(double_input)
        original_keys = set(self.patcher.model.state_dict())
        guard.install(self.patcher)
        state = getattr(self.patcher.model, guard._MARKER)
        self.assertEqual(len(state["references"]), 3)
        self.assertEqual(state["parameter_names"]["diffusion_model.simple"], "lin")
        self.assertEqual(tuple(state["references"]["diffusion_model.simple"].shape), (2, 3))
        with torch.no_grad():
            model.simple.lin.fill_(float("nan"))
            model.shared.lin.fill_(float("inf"))
        self.patcher.pre_run()
        guard.install(self.patcher.clone())
        for actual, expected in zip(model.simple(CUDAInput(simple_input)), expected_simple):
            self.assertTrue(torch.equal(actual, expected))
        for actual, expected in zip(model.shared(CUDAInput(double_input)), expected_double):
            self.assertTrue(torch.equal(actual, expected))
        self.assertTrue(all(dtype == torch.bfloat16 for _, dtype, _ in self.casts))
        self.assertEqual(set(self.patcher.model.state_dict()), original_keys)
        for name in ("simple", "shared"):
            with self.assertRaisesRegex(RuntimeError, "CUDA activations"):
                getattr(model, name)(torch.ones(1, 2, 3))

    def test_clone_refuses_protected_modulation_patches_accepts_linear_wrappers(self):
        guard.install(self.patcher)
        for name in ("simple", "shared"):
            clone = self.patcher.clone()
            clone.patches[f"diffusion_model.{name}.lin"] = [object()]
            with self.assertRaisesRegex(RuntimeError, "protected parameter patch"):
                clone.pre_run()
        clone = self.patcher.clone()
        clone.patches["diffusion_model.blocks.0.attn.wq.weight"] = [object()]
        clone.weight_wrapper_patches = {"diffusion_model.blocks.0.attn.wq.weight": [object()]}
        clone.pre_run()

    def test_per_run_integrity_detects_forward_reference_and_marker_mutation(self):
        for mutation in ("forward", "reference_identity", "reference_version", "marker"):
            patcher = Patcher()
            guard.install(patcher)
            state = getattr(patcher.model, guard._MARKER)
            if mutation == "forward":
                patcher.model.diffusion_model.simple.forward = lambda x: x
            elif mutation == "reference_identity":
                state["references"]["diffusion_model.shared"] = torch.zeros(18)
            elif mutation == "reference_version":
                state["references"]["diffusion_model.shared"].add_(1)
            else:
                setattr(patcher.model, guard._MARKER, {})
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                patcher.pre_run()

    def test_old_norm_only_marker_is_not_recaptured_or_silently_reused(self):
        guard.install(self.patcher)
        state = getattr(self.patcher.model, guard._MARKER)
        del state["schema"]
        with torch.no_grad():
            self.patcher.model.diffusion_model.simple.lin.fill_(float("nan"))
        with self.assertRaisesRegex(RuntimeError, "stale reference marker"):
            guard.install(self.patcher)



class DynamicPatcher(Patcher):
    def __init__(self):
        super().__init__()
        self.clone_calls = 0

    def is_dynamic(self):
        return True

    def clone(self, disable_dynamic=False):
        assert disable_dynamic is True
        self.clone_calls += 1
        result = CustomStaticPatcher()
        result.parent = self
        return result


class CustomStaticPatcher(Patcher):
    """Models an INT8 clone override retaining its custom static class."""
    pass


class StaticGuardTests(ModelGuardTests):
    # Reuse setup, not the inherited test cases (loaded separately below).
    def test_conversion_once_survives_node_cache_eviction_and_resident_nan(self):
        source = DynamicPatcher()
        first = guard.MATRIX_Krea2ModelGuard().guard(source)[0]
        self.assertIsInstance(first, CustomStaticPatcher)
        self.assertFalse(first.is_dynamic())
        self.assertIsNot(first.model, source.model)
        callback = first.get_callbacks("pre_run", guard._CALLBACK_KEY)[0]
        with torch.no_grad():
            first.model.diffusion_model.norm.scale.fill_(float("nan"))
        second = guard.MATRIX_Krea2ModelGuard().guard(source)[0]
        self.assertIs(second, first)
        self.assertEqual(source.clone_calls, 1)
        self.assertEqual(second.get_callbacks("pre_run", guard._CALLBACK_KEY), [callback])
        clone = first.clone()
        self.assertIsInstance(clone, CustomStaticPatcher)
        self.assertIs(guard.MATRIX_Krea2ModelGuard().guard(clone)[0], clone)
        self.assertIs(clone.get_callbacks("pre_run", guard._CALLBACK_KEY)[0], callback)
        clone.pre_run()

    def test_guarded_dynamic_and_patched_source_refused_before_clone(self):
        source = DynamicPatcher()
        guard.install(source)
        with self.assertRaisesRegex(RuntimeError, "already guarded dynamic"):
            guard._static_guard(source)
        self.assertEqual(source.clone_calls, 0)
        source = DynamicPatcher()
        source.patches["diffusion_model.linear.weight"] = [object()]
        with self.assertRaisesRegex(RuntimeError, "before diffusion LoRAs"):
            guard._static_guard(source)
        self.assertEqual(source.clone_calls, 0)

    def test_stale_cache_and_tampered_forward_refused_without_reload(self):
        for mutation in ("source_model", "delegate_model", "forward", "source_patch"):
            source = DynamicPatcher()
            delegate = guard._static_guard(source)
            if mutation == "source_model":
                source.model = Patcher().model
            elif mutation == "delegate_model":
                delegate.model = Patcher().model
            elif mutation == "forward":
                delegate.model.diffusion_model.norm.forward = lambda x: x
            else:
                source.object_patches["something"] = object()
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                guard._static_guard(source)
            self.assertEqual(source.clone_calls, 1)

    def test_cuda_source_and_clone_required(self):
        source = DynamicPatcher()
        source.load_device = torch.device("cpu")
        with self.assertRaisesRegex(RuntimeError, "CUDA"):
            guard._static_guard(source)
        self.assertEqual(source.clone_calls, 0)
        source.load_device = torch.device("cuda")
        result = CustomStaticPatcher()
        result.load_device = torch.device("cpu")
        source.clone = lambda **kw: result
        with self.assertRaisesRegex(RuntimeError, "CUDA"):
            guard._static_guard(source)
        self.assertFalse(hasattr(source, guard._STATIC_CACHE))

    def test_dynamic_or_shared_clone_refused(self):
        for result_kind in ("dynamic", "shared"):
            source = DynamicPatcher()
            result = DynamicPatcher() if result_kind == "dynamic" else CustomStaticPatcher()
            if result_kind == "shared":
                result.model = source.model
            source.clone = lambda **kw: result
            with self.assertRaisesRegex(RuntimeError, "independent native static"):
                guard._static_guard(source)

    def test_cache_lifetime_has_no_global_retention(self):
        import gc
        import weakref
        source = DynamicPatcher()
        delegate = guard._static_guard(source)
        source_ref, delegate_ref = weakref.ref(source), weakref.ref(delegate)
        del source, delegate
        gc.collect()
        self.assertIsNone(source_ref())
        self.assertIsNone(delegate_ref())


def load_tests(loader, tests, pattern):
    suite = loader.loadTestsFromTestCase(ModelGuardTests)
    for name in StaticGuardTests.__dict__:
        if name.startswith("test_"):
            suite.addTest(StaticGuardTests(name))
    return suite


if __name__ == "__main__":
    unittest.main()
