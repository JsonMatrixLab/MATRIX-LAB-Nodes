# MATRIX RESOLUTION

Class ID: `MATRIXLAB_Resolution`

Category: `MATRIX LAB/Resolution & Layout`

Calculates integer pixel dimensions without loading a model or allocating an image.

- Required controls: `aspect_ratio`, `resolution_tier`, `custom_width`, `custom_height`
- Ratios: `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, `2:3`, `4:5`, `Custom`
- Tiers: `1K`, `2K`, `4K`
- Outputs: `width` (`INT`), `height` (`INT`)

The tier sets the longer edge exactly to 1024, 2048, or 4096 pixels and rounds the shorter edge to the nearest integer. `Custom` returns each supplied whole-pixel side exactly within 1–16384. No hidden alignment is applied. These dimensions do not certify model compatibility.
