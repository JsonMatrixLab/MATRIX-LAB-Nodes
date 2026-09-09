# MATRIX EYE MASK

Class ID: `MATRIX_EyeMask`

Category: `MATRIX LAB/Masks & Detection`

Detects eye boxes, retains the highest-confidence candidates, optionally refines each with SAM, and returns union and per-eye masks.

- Required: `image` (`IMAGE`)
- Options: `detector` (registered `bbox/Eyeful_v2-Individual.pt`), `resolution` (`1280`), `threshold` (`0.5`), `min_size_px` (`24`), `max_eyes` (`2`), `sam_refine` (`true`), `feather_px` (`6`), `sam_erosion_px` (`10`)
- Outputs: `mask`, `masks`, `bboxes`, `preview`; all follow the pack's list-output contract

Selection is global per frame and ordered left-to-right after confidence filtering; it does not assign eyes to people. No detections return valid empty outputs. Missing or invalid detector/SAM assets and failed refinement raise an error rather than returning a misleading rectangle. Complete [detector and segmentation setup](../detector-setup.md) before execution.
