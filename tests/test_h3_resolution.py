"""Portable public-contract checks for MATRIX H3 Resolution."""
import unittest

from _core.resolution_h3_dimensions import H3ResolutionError, MATRIX_H3Resolution


class H3ResolutionPortableTests(unittest.TestCase):
    def test_public_contract_and_presets(self):
        node = MATRIX_H3Resolution()
        required = node.INPUT_TYPES()["required"]
        self.assertEqual(list(required), ["aspect_ratio", "resolution_tier", "custom_width", "custom_height"])
        self.assertEqual(node.RETURN_TYPES, ("INT", "INT"))
        self.assertEqual(node.RETURN_NAMES, ("width", "height"))
        self.assertEqual(node.calculate("9:16", "1K", 576, 1024), (576, 1024))
        self.assertEqual(node.calculate("16:9", "2K", 576, 1024), (2048, 1152))

    def test_custom_is_exact_and_grid_validated(self):
        node = MATRIX_H3Resolution()
        self.assertEqual(node.calculate("Custom", "2K", 640, 1088), (640, 1088))
        for invalid in (31, 33, 1000, 2049):
            with self.subTest(invalid=invalid), self.assertRaises(H3ResolutionError):
                node.calculate("Custom", "1K", invalid, 1024)


if __name__ == "__main__":
    unittest.main()
