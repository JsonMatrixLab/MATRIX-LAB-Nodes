"""Krea 2 workflow inventory and supported compatibility aliases."""
import json
from pathlib import Path
import unittest

from test_distribution import _load_pack


ALIASES = {
    "MATRIXSpectralSampler": "MATRIX_SpectralSampler",
    "MATRIXLAB_AIInfluencerResolution2K4K": "MATRIX_AIInfluencerResolution2K4K",
    "MATRIXLAB_ImageBatchLoader": "MATRIX_ImageBatchLoader",
    "MATRIXLAB_PromptDirector": "MATRIX_AutoPrompter",
}
RETIRED = {"MATRIX_CameraLook", "MATRIX_Renoise"}


class Krea2V1CompatibilityTests(unittest.TestCase):
    def test_example_uses_only_registered_matrix_nodes(self):
        pack = _load_pack()
        root = Path(__file__).resolve().parents[1]
        path = root / "examples/krea2-v1/MATRIX-Krea-2-AI-Influencer-4K-FP8-V1.api.json"
        graph = json.loads(path.read_bytes())
        needed = {
            node["class_type"]
            for node in graph.values()
            if node["class_type"].startswith("MATRIX")
        }
        self.assertTrue(RETIRED.isdisjoint(needed))
        self.assertTrue(needed.issubset(pack.NODE_CLASS_MAPPINGS), needed - set(pack.NODE_CLASS_MAPPINGS))
        self.assertIn("MATRIX_PhotoFinisher", needed)

    def test_legacy_names_preserve_current_schemas_and_functions(self):
        pack = _load_pack()
        for old, new in ALIASES.items():
            with self.subTest(node=old):
                child, parent = pack.NODE_CLASS_MAPPINGS[old], pack.NODE_CLASS_MAPPINGS[new]
                self.assertTrue(issubclass(child, parent))
                self.assertEqual(child.FUNCTION, parent.FUNCTION)
                self.assertEqual(child.INPUT_TYPES(), parent.INPUT_TYPES())

    def test_removed_finishing_classes_are_not_registered(self):
        pack = _load_pack()
        self.assertTrue(RETIRED.isdisjoint(pack.NODE_CLASS_MAPPINGS))


if __name__ == "__main__":
    unittest.main()
