# Changelog

User-visible changes are recorded here. This file describes package content; publication tags and release channels are separate facts.

## 0.2.0 - development candidate - 2026-09-09

- Unified the surviving execution and UI nodes into one package with six stable category directories.
- Preserved the public class IDs listed in `NODES.md` and retained `MATRIXLAB_EasyCrop`.
- Replaced the retired finishing pair with `MATRIX_PhotoFinisher`, a local deterministic Torch node with `Clean Digital`, `Everyday Capture`, and `Low Light` creative profiles.
- Set new Photo Finisher defaults to `Everyday Capture`, mix `1`, texture `1`, detail `1`, contrast `0`, warmth `0`, saturation `1`, and seed `42`.
- Simplified the general and AI-influencer resolution nodes to two integer outputs and included `MATRIXLAB_AIInfluencerResolution2K4K` for current Krea 2 geometry selection.
- Kept Prompt Director provider generation behind an explicit paid action; ordinary graph execution returns saved text without a network request.
- Added public installation, migration, compatibility, node, license-notice, and agent-installation documentation.

Full live acceptance of the current bytes across both ComfyUI renderers and all model-dependent paths remains pending.

## 0.1.0

- Initial unified-package development metadata.
