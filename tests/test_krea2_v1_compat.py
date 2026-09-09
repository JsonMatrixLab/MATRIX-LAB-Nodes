"""V1 inventory and retained finishing behavior, without ComfyUI or GPU."""
import asyncio
import json
from pathlib import Path
import unittest
import torch
from test_distribution import _load_pack


class Krea2V1CompatibilityTests(unittest.TestCase):
    def test_example_has_every_matrix_node_registered(self):
        pack = _load_pack()
        path = Path(__file__).resolve().parents[1] / 'examples/krea2-v1/MATRIX-Krea-2-AI-Influencer-4K-FP8-V1.api.json'
        graph = json.loads(path.read_bytes())
        needed = {n['class_type'] for n in graph.values() if n['class_type'].startswith('MATRIX')}
        self.assertTrue(needed.issubset(pack.NODE_CLASS_MAPPINGS), needed-set(pack.NODE_CLASS_MAPPINGS))
        self.assertEqual(graph['116']['class_type'], 'MATRIX_MetadataKiller')
        self.assertEqual(graph['18']['inputs']['model'], ['306',0])

    def test_legacy_names_preserve_current_schemas_and_functions(self):
        pack = _load_pack()
        aliases = {'MATRIXSpectralSampler':'MATRIX_SpectralSampler',
                   'MATRIXLAB_AIInfluencerResolution2K4K':'MATRIX_AIInfluencerResolution2K4K',
                   'MATRIXLAB_ImageBatchLoader':'MATRIX_ImageBatchLoader',
                   'MATRIXLAB_PromptDirector':'MATRIX_AutoPrompter'}
        for old, new in aliases.items():
            with self.subTest(node=old):
                child, parent = pack.NODE_CLASS_MAPPINGS[old], pack.NODE_CLASS_MAPPINGS[new]
                self.assertTrue(issubclass(child,parent))
                self.assertEqual(child.FUNCTION,parent.FUNCTION)
                self.assertEqual(child.INPUT_TYPES(),parent.INPUT_TYPES())

    def test_retained_finishing_runs_without_changing_source(self):
        pack = _load_pack()
        image = torch.full((1,32,32,3),.5)
        original = image.clone()
        camera = pack.NODE_CLASS_MAPPINGS['MATRIX_CameraLook']()
        result = asyncio.run(camera.execute(image=image,enabled=False))
        self.assertTrue(torch.equal(result[0], image))
        renoise = pack.NODE_CLASS_MAPPINGS['MATRIX_Renoise']()
        inputs = dict(image=image,grain_seed=420011,iso_preset='ISO 800',strength=.4)
        first = asyncio.run(renoise.execute(**inputs))[0]
        second = asyncio.run(renoise.execute(**inputs))[0]
        self.assertTrue(torch.equal(first,second))
        self.assertTrue(torch.equal(image,original))
        self.assertTrue(torch.isfinite(first).all())
        self.assertFalse(torch.equal(first,image))
