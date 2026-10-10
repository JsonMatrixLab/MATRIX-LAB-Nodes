# MATRIX QWEN IMAGE 2.1 RESOLUTION

This geometry utility has one canonical `aspect_ratio` widget and exactly two `INT`
outputs named `width` and `height`. The default and HALO **RESET** state are both
`1:1`.

| Aspect ratio | Width x height |
|---|---|
| 1:1 | 2048 x 2048 |
| 4:3 | 2400 x 1792 |
| 3:4 | 1792 x 2400 |
| 3:2 | 2528 x 1696 |
| 2:3 | 1696 x 2528 |
| 16:9 | 2752 x 1536 |
| 9:16 | 1536 x 2752 |

These seven entries are pinned to the native-size table in the Hugging Face model
card for `Qwen/Qwen-Image-2.1`. Every dimension is a multiple of 32, the longest
side is at most 2752 pixels, and the area is at most 4,300,800 pixels. Unknown
ratios are rejected. The node does not offer custom dimensions or resolution tiers.

The node performs no model loading, inference, image transform, crop, or upscale.
Connect its outputs to the corresponding width and height inputs of a compatible
generation workflow.

The HALO controls, all seven selections, RESET, saved state, and queue path were
verified locally in renderer Classic and renderer Nodes 2.0 with ComfyUI 0.37.0 and
frontend 1.53.6. A Pod run is **NOT TESTED**. This node-level check does not certify
a Qwen Image 2.1 model render or other nodes in the pack.

Qwen Image 2.1 uses the Qwen Research License and is a non-commercial model. This
table node ships no model and does not change the model's license or permitted use.
