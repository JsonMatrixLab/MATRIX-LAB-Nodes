# MATRIX AI INFLUENCER RESOLUTION

Class ID: `MATRIX_AIInfluencerResolution`


Category: `MATRIX LAB/Resolution & Layout`

A focused, model-independent pixel selector for portrait-oriented workflows.

- Required: `aspect_ratio` (`1:1`, `9:16`, or `3:4`; default `3:4`), `resolution_tier` (`1K`, `2K`, or `4K`; default `2K`)
- Outputs: `width` (`INT`), `height` (`INT`)

The selected tier is an exact longer edge of 1024, 2048, or 4096 pixels. For example, `3:4` at `2K` returns 1536 by 2048. The node returns geometry only: it has no sampler plan, delivery-size outputs, model checks, or claim that a connected model supports the result. Older six-output workflows require manual migration.
