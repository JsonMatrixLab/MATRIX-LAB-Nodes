from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

import torch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "matrix_lab_scail_window_runtime",
    ROOT / "_core/sample_scail_window/__init__.py",
)
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


def fixture(count: int):
    pose = torch.arange(count, dtype=torch.float32).div(max(count, 1)).view(count, 1, 1, 1).expand(count, 32, 32, 3)
    mask = torch.zeros_like(pose).clone()
    return dict(
        model=object(), positive={}, negative={}, vae=NS(), pose_video=pose,
        pose_video_mask=mask, reference_image=pose[:1], reference_image_mask=mask[:1],
        width=32, height=32, frame_count=count, seed=123, steps=40, cfg=5.0,
        denoise=1.0, sampler_name="uni_pc", scheduler="simple", pose_strength=1.0,
        pose_start=0.0, pose_end=1.0, replacement_mode=False,
    )


class ScailWindowTests(unittest.TestCase):
    def test_all_frame_plans_follow_81_5_76_contract(self):
        for count in range(1, 16385):
            aligned, continuations, coverage = runtime.plan_frames(count)
            self.assertGreaterEqual(aligned, count)
            self.assertLess(aligned - count, 4)
            self.assertEqual(aligned % 4, 1)
            self.assertEqual(coverage, aligned if continuations == 0 else 81 + 76 * continuations)

    def test_exact_n_output_across_window_boundaries(self):
        for count in (1, 5, 80, 81, 82, 156, 157, 158, 233, 234, 321):
            with self.subTest(count=count):
                item = fixture(count)
                calls = []

                def condition(**kwargs):
                    index = len(calls)
                    start = 76 * index
                    length = kwargs["length"]
                    pixels = kwargs["pose_video"][start:start + length].clone()
                    calls.append(kwargs)
                    return ({}, {}, {"pixels": pixels}, start + length)

                def sample(**kwargs):
                    return (kwargs["latent_image"],)

                def decode(**kwargs):
                    return (kwargs["samples"]["pixels"],)

                images, = runtime.run_windows(item, condition, sample, decode)
                self.assertEqual(images.shape[0], count)
                self.assertTrue(torch.equal(images, item["pose_video"]))
                self.assertEqual(len(calls), runtime.plan_frames(count)[1] + 1)

    def test_limits_fail_before_inference(self):
        def forbidden(**_kwargs):
            self.fail("invalid input reached inference")

        cases = (
            {"width": 33}, {"height": 0}, {"frame_count": 0}, {"seed": -1},
            {"steps": 0}, {"cfg": float("nan")}, {"pose_start": 0.9, "pose_end": 0.1},
            {"replacement_mode": 1}, {"pose_video": torch.ones(1, 32, 32, 4)},
        )
        for change in cases:
            with self.subTest(change=tuple(change)), self.assertRaises(ValueError):
                item = {**fixture(1), **change}
                runtime.run_windows(item, forbidden, forbidden, forbidden)


if __name__ == "__main__":
    unittest.main()
