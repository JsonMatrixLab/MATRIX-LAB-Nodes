# MATRIX AI INFLUENCER RESOLUTION 2K/4K

Class ID: `MATRIXLAB_AIInfluencerResolution2K4K`

Category: `MATRIX LAB/Resolution & Layout`

This class uses the same pixel calculation as MATRIX AI INFLUENCER RESOLUTION while exposing only `2K` and `4K`.

- Required: `aspect_ratio` (`1:1`, `9:16`, or `3:4`), `resolution_tier` (`2K` or `4K`)
- Outputs: `width` (`INT`), `height` (`INT`)

It rejects `1K` and returns geometry only. It does not connect or validate a model or sampler and is not a replacement for the retired `MATRIXLAB_Resolution2K` or `MATRIXLAB_Resolution4KProgressive` ABI.
