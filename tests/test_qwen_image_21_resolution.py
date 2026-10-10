"""Portable public-contract checks for MATRIX Qwen Image 2.1 Resolution."""
import unittest

from _core.resolution_qwen_image_21_dimensions import (
    ASPECT_RATIOS,
    MAX_AREA,
    MAX_LONGEST_SIDE,
    MATRIX_QwenImage21Resolution,
    NATIVE_SIZES,
    QwenImage21ResolutionError,
    validate_qwen_image_21_dimensions,
)


PINNED_HF_TABLE = {
    "1:1": (2048, 2048),
    "4:3": (2400, 1792),
    "3:4": (1792, 2400),
    "3:2": (2528, 1696),
    "2:3": (1696, 2528),
    "16:9": (2752, 1536),
    "9:16": (1536, 2752),
}


class QwenImage21ResolutionPortableTests(unittest.TestCase):
    def test_public_contract_and_default(self):
        required = MATRIX_QwenImage21Resolution.INPUT_TYPES()["required"]
        self.assertEqual(list(required), ["aspect_ratio"])
        self.assertEqual(required["aspect_ratio"][0], list(PINNED_HF_TABLE))
        self.assertEqual(required["aspect_ratio"][1]["default"], "1:1")
        self.assertEqual(MATRIX_QwenImage21Resolution.RETURN_TYPES, ("INT", "INT"))
        self.assertEqual(MATRIX_QwenImage21Resolution.RETURN_NAMES, ("width", "height"))
        self.assertEqual(MATRIX_QwenImage21Resolution.OUTPUT_IS_LIST, (False, False))
        self.assertEqual(
            MATRIX_QwenImage21Resolution.CATEGORY,
            "MATRIX LAB/Resolution & Layout",
        )

    def test_all_seven_hugging_face_table_rows_are_exact(self):
        node = MATRIX_QwenImage21Resolution()
        self.assertEqual(ASPECT_RATIOS, tuple(PINNED_HF_TABLE))
        self.assertEqual(NATIVE_SIZES, PINNED_HF_TABLE)
        for ratio, expected in PINNED_HF_TABLE.items():
            with self.subTest(ratio=ratio):
                self.assertEqual(node.calculate(ratio), expected)
                width, height = expected
                self.assertEqual(width % 32, 0)
                self.assertEqual(height % 32, 0)
                self.assertLessEqual(max(width, height), MAX_LONGEST_SIDE)
                self.assertLessEqual(width * height, MAX_AREA)

    def test_limits_and_unknown_ratio_are_rejected(self):
        self.assertEqual(MAX_LONGEST_SIDE, 2752)
        self.assertEqual(MAX_AREA, 4_300_800)
        for dimensions in ((33, 32), (2784, 32), (2400, 1824), (0, 32)):
            with self.subTest(dimensions=dimensions), self.assertRaises(
                QwenImage21ResolutionError
            ):
                validate_qwen_image_21_dimensions(*dimensions)
        with self.assertRaises(QwenImage21ResolutionError):
            MATRIX_QwenImage21Resolution().calculate("21:9")


if __name__ == "__main__":
    unittest.main()
