# MATRIX FLUX 3 KLEIN RESOLUTION

This geometry utility has canonical `aspect_ratio` and `resolution` widgets and
exactly two `INT` outputs named `width` and `height`. The defaults and HALO
**RESET** state are `1:1` and `1K`.

| Resolution | 1:1 | 4:3 | 3:4 | 3:2 | 2:3 | 16:9 | 9:16 |
|---|---|---|---|---|---|---|---|
| 1K | 1024 x 1024 | 1184 x 880 | 880 x 1184 | 1248 x 832 | 832 x 1248 | 1360 x 768 | 768 x 1360 |
| 1.5K | 1536 x 1536 | 1776 x 1328 | 1328 x 1776 | 1888 x 1248 | 1248 x 1888 | 2048 x 1152 | 1152 x 2048 |
| 2K | 2048 x 2048 | 2352 x 1776 | 1776 x 2352 | 2496 x 1680 | 1680 x 2496 | 2720 x 1536 | 1536 x 2720 |
| 4K | 4096 x 4096 | 4096 x 3088 | 3088 x 4096 | 4096 x 2752 | 2752 x 4096 | 4096 x 2320 | 2320 x 4096 |

The frozen table follows the FLUX 3 Klein geometry boundary. Every dimension is a
positive multiple of 16, the longest side is at most 4096 pixels, and the area does
not exceed the selected tier's square canvas. Unknown ratios, tiers, or dimensions
are rejected.

The node performs no model loading, inference, image transform, crop, or upscale.
Connect its outputs to the corresponding width and height inputs of a compatible
generation workflow.

All 28 sizes, RESET, saved state, the queue path, and a simulated FLUX 3 graph were
verified locally in renderer Classic and renderer Nodes 2.0 with ComfyUI 0.37.0 on
2026-10-15. A real FLUX 3 render, image quality above 1K, VRAM per tier, forced
frontend mount failure, and a complete v2 Pod acceptance pass are **NOT TESTED**.
