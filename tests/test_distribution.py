"""Acceptance tests that run from the standalone public repository.

The suite intentionally uses only files shipped in the distribution. It does not
need the private Factory, retained runtime proof, ComfyUI, or provider access.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import importlib.util
import inspect
import json
from pathlib import Path
import re
import socket
import sys
import unittest
from unittest import mock

import torch


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "matrixlab_public_distribution_under_test"
RETIRED_NODE_IDS = {"MATRIX_CameraLook", "MATRIX_Renoise"}
COMPAT_NODE_IDS = RETIRED_NODE_IDS | {"MATRIXSpectralSampler", "MATRIXLAB_AIInfluencerResolution2K4K", "MATRIXLAB_ImageBatchLoader", "MATRIXLAB_PromptDirector"}
BASE_NODE_IDS = {
    "MATRIX_AIInfluencerResolution",
    "MATRIX_EasyCrop",
    "MATRIX_ImageBatchLoader",
    "MATRIX_AutoPrompter",
    "MATRIX_Resolution",
    "MATRIX_SpectralSampler",
    "MATRIX_CropTailPaste",
    "MATRIX_EyeMask",
    "MATRIX_LatentTail",
    "MATRIX_OutputStage",
    "MATRIX_PhotoFinisher",
    "MATRIX_MetadataKiller",
    "MATRIX_SkinMask",
}
ADDITIVE_NODE_ID = "MATRIX_AIInfluencerResolution2K4K"
NODE_DIRECTORIES = {
    "image_processing",
    "input_output",
    "masks_detection",
    "prompting",
    "resolution_layout",
    "sampling_detail",
}
PHOTO_DEFAULTS = {
    "profile": "Everyday Capture",
    "mix": 1.0,
    "texture": 1.0,
    "detail": 1.0,
    "contrast": 0.0,
    "warmth": 0.0,
    "saturation": 1.0,
    "seed": 42,
}


def _load_pack():
    """Import the checkout as a package even when its directory has a hyphen."""
    existing = sys.modules.get(PACKAGE_NAME)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not create an import spec for the distribution")
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(PACKAGE_NAME, None)
        raise
    return module


class DistributionStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
        cls.pack = _load_pack()

    def test_manifest_matches_imported_inventory_and_categories(self):
        imported_ids = set(self.pack.NODE_CLASS_MAPPINGS)
        self.assertEqual(imported_ids, BASE_NODE_IDS | COMPAT_NODE_IDS | {ADDITIVE_NODE_ID, "MATRIX_Krea2CLIPLoader", "MATRIX_Krea2ModelGuard"})
        self.assertEqual(imported_ids, set(self.manifest["nodes"]))
        self.assertEqual(imported_ids, set(self.manifest["categories"]))
        self.assertEqual(imported_ids, set(self.pack.NODE_DISPLAY_NAME_MAPPINGS))
        self.assertEqual(len(self.pack.NODE_CLASS_MAPPINGS), len(set(self.pack.NODE_CLASS_MAPPINGS.values())))
        for node_id, node_class in self.pack.NODE_CLASS_MAPPINGS.items():
            with self.subTest(node_id=node_id):
                self.assertEqual(node_class.CATEGORY, self.manifest["categories"][node_id])

    def test_package_and_manifest_versions_agree(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"\s*$', pyproject, flags=re.MULTILINE)
        self.assertIsNotNone(match, "pyproject.toml must declare a project version")
        self.assertEqual(match.group(1), self.manifest["version"])

    def test_class_ids_match_public_product_names(self):
        for node_id, display in self.pack.NODE_DISPLAY_NAME_MAPPINGS.items():
            if node_id in COMPAT_NODE_IDS:
                continue
            with self.subTest(node_id=node_id):
                self.assertRegex(node_id, r"^MATRIX_[A-Z][A-Za-z0-9]*$")
                self.assertTrue(display.startswith("MATRIX "))
                self.assertEqual(node_id[len("MATRIX_"):].upper(),
                                 re.sub(r"[^A-Z0-9]", "", display[len("MATRIX "):]))

    def test_distribution_has_exactly_the_six_public_node_directories(self):
        actual = {
            path.name
            for path in (ROOT / "nodes").iterdir()
            if path.is_dir() and path.name != "__pycache__"
        }
        self.assertEqual(actual, NODE_DIRECTORIES)
        self.assertEqual({path.name for path in (ROOT / "nodes").glob("*.py")}, {"__init__.py"})

    def test_krea2_v1_compatibility_ids_are_registered(self):
        visible_ids = (
            set(self.manifest["nodes"])
            | set(self.manifest["categories"])
            | set(self.pack.NODE_CLASS_MAPPINGS)
            | set(self.pack.NODE_DISPLAY_NAME_MAPPINGS)
        )
        self.assertTrue(COMPAT_NODE_IDS.issubset(visible_ids))
        implementation = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "nodes").rglob("*.py")
        )
        for retired in RETIRED_NODE_IDS:
            self.assertIn(retired, implementation)

    def test_runtime_and_font_asset_hashes_match(self):
        runtime_registry = ROOT / "_core" / "runtime-assets.json"
        self.assertEqual(
            hashlib.sha256(runtime_registry.read_bytes()).hexdigest(),
            self.manifest["runtime_asset_registry_sha256"],
        )
        font_manifest = json.loads(
            (ROOT / "web" / "assets" / "font-manifest.json").read_text(encoding="utf-8")
        )
        assets = ROOT / "web" / "assets"
        for file_key, hash_key in (
            ("font_file", "font_sha256"),
            ("license_file", "license_sha256"),
        ):
            with self.subTest(asset=font_manifest[file_key]):
                asset = assets / font_manifest[file_key]
                self.assertTrue(asset.is_file())
                self.assertEqual(hashlib.sha256(asset.read_bytes()).hexdigest(), font_manifest[hash_key])
        license_text = (assets / font_manifest["license_file"]).read_text(encoding="utf-8")
        self.assertEqual(font_manifest["license"], "OFL-1.1")
        self.assertIn("SIL OPEN FONT LICENSE", license_text.upper())
        self.assertTrue((ROOT / "LICENSE").is_file())

    def test_readme_local_links_resolve_inside_the_repository(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        links = re.findall(r"\[[^]]+\]\(([^)]+)\)", readme)
        local_links = [link.split("#", 1)[0] for link in links if "://" not in link and not link.startswith("#")]
        self.assertTrue(local_links, "README should include navigable local links")
        root_resolved = ROOT.resolve()
        for link in local_links:
            with self.subTest(link=link):
                target = (ROOT / link).resolve()
                self.assertTrue(target == root_resolved or root_resolved in target.parents)
                self.assertTrue(target.exists())

    def test_example_has_consistent_unselected_input_and_connected_defaults(self):
        graph = json.loads((ROOT / "examples/photo-finisher.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual({node["type"] for node in nodes.values()},
                         {"LoadImage", "MATRIX_PhotoFinisher", "PreviewImage"})
        for node in nodes.values():
            self.assertNotIn("widgets_values_named", node, "avoid stale parallel widget state")
            if node["type"] == "LoadImage":
                self.assertEqual(node["widgets_values"][0], "")
            elif node["type"] == "MATRIX_PhotoFinisher":
                self.assertEqual(node["widgets_values"], list(PHOTO_DEFAULTS.values()))
        self.assertEqual(len(graph["links"]), 2)
        for link_id, origin, origin_slot, target, target_slot, socket_type in graph["links"]:
            self.assertIn(link_id, nodes[origin]["outputs"][origin_slot]["links"])
            self.assertEqual(nodes[target]["inputs"][target_slot]["link"], link_id)
            self.assertEqual(socket_type, "IMAGE")


class PhotoFinisherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = _load_pack()
        cls.node_class = cls.pack.NODE_CLASS_MAPPINGS["MATRIX_PhotoFinisher"]
        cls.api = importlib.import_module(f"{PACKAGE_NAME}._core.image_photo_finisher")

    def test_public_defaults_are_stable_and_match_the_core_api(self):
        optional = self.node_class.INPUT_TYPES()["optional"]
        actual = {name: optional[name][1]["default"] for name in PHOTO_DEFAULTS}
        self.assertEqual(actual, PHOTO_DEFAULTS)
        parameters = inspect.signature(self.api.photo_finish).parameters
        self.assertEqual({name: parameters[name].default for name in PHOTO_DEFAULTS}, PHOTO_DEFAULTS)
        self.assertIs(optional["seed"][1]["control_after_generate"], False)

    def test_cpu_output_is_repeatable_batch_safe_and_preserves_alpha(self):
        rgb = torch.linspace(0.1, 0.9, 2 * 17 * 19 * 3).reshape(2, 17, 19, 3)
        alpha = torch.linspace(0.0, 1.0, 2 * 17 * 19).reshape(2, 17, 19, 1)
        image = torch.cat((rgb, alpha), dim=-1)
        before = image.clone()
        first = self.api.photo_finish(image)
        second = self.api.photo_finish(image)
        self.assertTrue(torch.equal(first, second))
        self.assertTrue(torch.equal(image, before))
        self.assertTrue(torch.equal(first[..., 3], image[..., 3]))
        self.assertFalse(torch.equal(first[..., :3], image[..., :3]))
        self.assertEqual(first.shape, image.shape)
        self.assertEqual(first.device.type, "cpu")

    def test_zero_saturation_is_grayscale_with_default_texture(self):
        image = torch.rand(2, 17, 19, 3, generator=torch.Generator().manual_seed(71))
        for profile in self.api.PROFILES:
            with self.subTest(profile=profile):
                result = self.api.photo_finish(image, profile=profile, saturation=0.0)
                self.assertTrue(torch.equal(result[..., 0], result[..., 1]))
                self.assertTrue(torch.equal(result[..., 1], result[..., 2]))

    def test_mix_zero_is_exact_identity(self):
        image = torch.rand(2, 13, 11, 3)
        result = self.api.photo_finish(image, mix=0.0)
        self.assertIs(result, image)
        self.assertTrue(torch.equal(result, image))

    def test_mask_zero_preserves_and_soft_mask_blends(self):
        image = torch.linspace(0.1, 0.9, 15 * 21 * 3).reshape(1, 15, 21, 3)
        full = self.api.photo_finish(image, seed=17)
        mask = torch.full((1, 15, 21), 0.5)
        mask[:, :, 0] = 0.0
        masked = self.api.photo_finish(image, mask, seed=17)
        self.assertTrue(torch.equal(masked[:, :, 0], image[:, :, 0]))
        torch.testing.assert_close(
            masked[:, :, 1:],
            (image[:, :, 1:] + full[:, :, 1:]) / 2,
            rtol=0.0,
            atol=2e-7,
        )

    def test_compiled_node_executes_actual_cpu_operation(self):
        image = torch.full((2, 9, 7, 3), 0.45)
        result, = asyncio.run(self.node_class().execute(image=image))
        expected = self.api.photo_finish(image)
        self.assertTrue(torch.equal(result, expected))


class OfflineNodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = _load_pack()

    def test_prompt_director_manual_execution_returns_saved_text(self):
        node = self.pack.NODE_CLASS_MAPPINGS["MATRIX_AutoPrompter"]()
        saved = "  a manually edited prompt; no provider call  "
        with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network attempted")):
            self.assertEqual(node.execute(final_prompt=saved), (saved,))
        self.assertEqual(node.check_lazy_status(), [])

    def test_additive_resolution_node_returns_all_six_dimensions_when_present(self):
        node_id = ADDITIVE_NODE_ID
        if node_id not in self.pack.NODE_CLASS_MAPPINGS:
            self.skipTest("base distribution does not include the additive 2K/4K node")
        node = self.pack.NODE_CLASS_MAPPINGS[node_id]()
        expected = {
            ("1:1", "2K"): (2048, 2048),
            ("1:1", "4K"): (4096, 4096),
            ("9:16", "2K"): (1152, 2048),
            ("9:16", "4K"): (2304, 4096),
            ("3:4", "2K"): (1536, 2048),
            ("3:4", "4K"): (3072, 4096),
        }
        for (ratio, tier), dimensions in expected.items():
            with self.subTest(ratio=ratio, tier=tier):
                self.assertEqual(
                    asyncio.run(node.execute(aspect_ratio=ratio, resolution_tier=tier)),
                    dimensions,
                )


if __name__ == "__main__":
    unittest.main()
