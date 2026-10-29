"""Portable public-contract checks for MATRIX FLUX 3 Klein Resolution."""
import unittest

from _core.resolution_flux_3_klein_dimensions import (
    ASPECT_RATIOS,
    GRID,
    MAX_LONGEST_SIDE,
    MATRIX_Flux3KleinResolution,
    RESOLUTIONS,
    SIZES,
    TIER_SIDE,
    Flux3KleinResolutionError,
    validate_flux_3_klein_dimensions,
)


PINNED_TABLE = {
    "1K": {
        "1:1": (1024, 1024), "4:3": (1184, 880), "3:4": (880, 1184),
        "3:2": (1248, 832), "2:3": (832, 1248), "16:9": (1360, 768),
        "9:16": (768, 1360),
    },
    "1.5K": {
        "1:1": (1536, 1536), "4:3": (1776, 1328), "3:4": (1328, 1776),
        "3:2": (1888, 1248), "2:3": (1248, 1888), "16:9": (2048, 1152),
        "9:16": (1152, 2048),
    },
    "2K": {
        "1:1": (2048, 2048), "4:3": (2352, 1776), "3:4": (1776, 2352),
        "3:2": (2496, 1680), "2:3": (1680, 2496), "16:9": (2720, 1536),
        "9:16": (1536, 2720),
    },
    "4K": {
        "1:1": (4096, 4096), "4:3": (4096, 3088), "3:4": (3088, 4096),
        "3:2": (4096, 2752), "2:3": (2752, 4096), "16:9": (4096, 2320),
        "9:16": (2320, 4096),
    },
}


class Flux3KleinResolutionPortableTests(unittest.TestCase):
    def test_public_contract_and_defaults(self):
        required = MATRIX_Flux3KleinResolution.INPUT_TYPES()["required"]
        self.assertEqual(list(required), ["aspect_ratio", "resolution"])
        self.assertEqual(required["aspect_ratio"][0], list(ASPECT_RATIOS))
        self.assertEqual(required["aspect_ratio"][1]["default"], "1:1")
        self.assertEqual(required["resolution"][0], list(RESOLUTIONS))
        self.assertEqual(required["resolution"][1]["default"], "1K")
        self.assertEqual(MATRIX_Flux3KleinResolution.RETURN_TYPES, ("INT", "INT"))
        self.assertEqual(MATRIX_Flux3KleinResolution.RETURN_NAMES, ("width", "height"))
        self.assertEqual(MATRIX_Flux3KleinResolution.OUTPUT_IS_LIST, (False, False))
        self.assertEqual(
            MATRIX_Flux3KleinResolution.CATEGORY,
            "MATRIX LAB/Resolution & Layout",
        )

    def test_all_28_frozen_table_rows_are_exact(self):
        node = MATRIX_Flux3KleinResolution()
        self.assertEqual(ASPECT_RATIOS, tuple(PINNED_TABLE["1K"]))
        self.assertEqual(RESOLUTIONS, tuple(PINNED_TABLE))
        self.assertEqual(SIZES, PINNED_TABLE)
        for resolution, rows in PINNED_TABLE.items():
            for ratio, expected in rows.items():
                with self.subTest(resolution=resolution, ratio=ratio):
                    self.assertEqual(node.calculate(ratio, resolution), expected)
                    width, height = expected
                    self.assertEqual(width % GRID, 0)
                    self.assertEqual(height % GRID, 0)
                    self.assertLessEqual(max(width, height), MAX_LONGEST_SIDE)
                    self.assertLessEqual(width * height, TIER_SIDE[resolution] ** 2)

    def test_limits_and_unknown_values_are_rejected(self):
        self.assertEqual(GRID, 16)
        self.assertEqual(MAX_LONGEST_SIDE, 4096)
        for dimensions, resolution in (
            ((17, 16), "1K"), ((4112, 16), "4K"), ((1040, 1024), "1K"),
            ((0, 16), "1K"),
        ):
            with self.subTest(dimensions=dimensions), self.assertRaises(
                Flux3KleinResolutionError
            ):
                validate_flux_3_klein_dimensions(*dimensions, resolution)
        with self.assertRaises(Flux3KleinResolutionError):
            MATRIX_Flux3KleinResolution().calculate("21:9", "1K")
        with self.assertRaises(Flux3KleinResolutionError):
            MATRIX_Flux3KleinResolution().calculate("1:1", "8K")


if __name__ == "__main__":
    unittest.main()
