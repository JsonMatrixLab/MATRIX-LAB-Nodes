"""Portable regression for the shipped SAM image-embedding cache.

The predictor is a CPU fake; tests execute the actual distributed adapter function.
They do not assert detector quality, GPU behavior, or unrelated runtime readiness.
"""
from __future__ import annotations

import ast
import gc
from pathlib import Path
import types
import unittest
from unittest import mock
import weakref
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

import numpy as np


class SamImageCacheTests(unittest.TestCase):
    def setUp(self):
        runtime = Path(__file__).resolve().parents[1] / "_core" / "runtime_bootstrap.py"
        tree = ast.parse(runtime.read_text(encoding="utf-8"))
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == "_eye_mask_adapters")
        namespace = {
            "_load_registry": lambda: {},
            "_asset_by_role": lambda registry, role: {"logical_id": role},
            "_verified_asset": lambda paths, entry: (None, Path("fixture-model")),
            "id": lambda value: 7,  # deterministically collide the former id+shape key
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(runtime), "exec"), namespace)
        instances = []

        class Model:
            def to(self, **kwargs):
                return self
            def eval(self):
                return self

        class Predictor:
            def __init__(self, model):
                self.images = []
                self.fail_next = False
                instances.append(self)

            def set_image(self, pixels):
                if self.fail_next:
                    self.fail_next = False
                    raise RuntimeError("injected encoder failure")
                self.images.append(pixels.copy())

            def predict(self, **kwargs):
                pixels = self.images[-1]
                mask = np.full(pixels.shape[:2], int(pixels[0, 0, 0]), dtype=np.float32)
                return np.stack([mask]), np.array([1.0]), None

        ultra = types.ModuleType("ultralytics")
        ultra.YOLO = lambda path: object()
        segment = types.ModuleType("segment_anything")
        segment.SamPredictor = Predictor
        segment.sam_model_registry = {"vit_b": lambda **kwargs: Model()}
        self.imports = mock.patch.dict("sys.modules", {"ultralytics": ultra, "segment_anything": segment})
        self.imports.start()
        self.addCleanup(self.imports.stop)
        _, self.refine = namespace["_eye_mask_adapters"](
            None, types.SimpleNamespace(get_torch_device=lambda: "cpu"))
        self.instances = instances

    def run_refine(self, image):
        return self.refine(image, (0, 0, 4, 4), (2, 2))

    def test_unchanged_reuses_but_mutation_and_new_image_refresh(self):
        first = np.zeros((8, 8, 3), dtype=np.uint8)
        self.run_refine(first)
        self.run_refine(first)
        first[0, 0, 0] = 1
        self.assertEqual(float(self.run_refine(first)[0, 0]), 1)
        second = np.full(first.shape, 2, dtype=np.uint8)
        self.assertEqual(float(self.run_refine(second)[0, 0]), 2)
        self.run_refine(second)
        self.assertEqual([int(x[0, 0, 0]) for x in self.instances[0].images], [0, 1, 2])

    def test_noncontiguous_same_view_reuses_and_mutation_refreshes(self):
        base = np.zeros((8, 16, 3), dtype=np.uint8)
        image = base[:, ::2]
        self.assertFalse(image.flags.c_contiguous)
        self.run_refine(image)
        self.run_refine(image)
        base[0, 0, 0] = 9
        self.assertEqual(float(self.run_refine(image)[0, 0]), 9)
        self.assertEqual(len(self.instances[0].images), 2)

    def test_cache_does_not_keep_input_alive_and_new_object_refreshes(self):
        first = np.zeros((8, 8, 3), dtype=np.uint8)
        pointer = weakref.ref(first)
        self.run_refine(first)
        del first
        gc.collect()
        self.assertIsNone(pointer())
        self.run_refine(np.full((8, 8, 3), 3, dtype=np.uint8))
        self.assertEqual(len(self.instances[0].images), 2)

    def test_concurrent_refinements_cannot_swap_embeddings(self):
        self.run_refine(np.zeros((8, 8, 3), dtype=np.uint8))
        predictor = self.instances[0]
        predict_original = predictor.predict
        first_inside = threading.Event()
        second_started = threading.Event()
        allow_first = threading.Event()

        def predict(**kwargs):
            if threading.current_thread().name.startswith("sam-first"):
                first_inside.set()
                if not allow_first.wait(3):
                    raise RuntimeError("test coordination timeout")
            return predict_original(**kwargs)

        predictor.predict = predict
        first = np.full((8, 8, 3), 1, dtype=np.uint8)
        second = np.full(first.shape, 2, dtype=np.uint8)

        def second_call():
            second_started.set()
            return self.run_refine(second)

        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="sam-first") as a, \
             ThreadPoolExecutor(max_workers=1, thread_name_prefix="sam-second") as b:
            result_a = a.submit(self.run_refine, first)
            self.assertTrue(first_inside.wait(3))
            result_b = b.submit(second_call)
            self.assertTrue(second_started.wait(3))
            try:
                with self.assertRaises(FutureTimeoutError):
                    result_b.result(timeout=0.05)
            finally:
                allow_first.set()
            self.assertEqual(float(result_a.result(timeout=3)[0, 0]), 1)
            self.assertEqual(float(result_b.result(timeout=3)[0, 0]), 2)

    def test_failed_refresh_retries_before_prediction(self):
        first = np.zeros((8, 8, 3), dtype=np.uint8)
        self.run_refine(first)
        second = np.full(first.shape, 5, dtype=np.uint8)
        self.instances[0].fail_next = True
        with self.assertRaisesRegex(RuntimeError, "injected encoder failure"):
            self.run_refine(second)
        self.assertEqual(float(self.run_refine(second)[0, 0]), 5)
        self.assertEqual(len(self.instances[0].images), 2)


if __name__ == "__main__":
    unittest.main()

