# Changelog

User-visible changes are recorded here. This file describes package content; publication tags and release channels are separate facts.

## 0.3.1 - development candidate - 2026-09-09

- Metadata Killer displays a small, metadata-verified preview while keeping the verified full-resolution original for opening and downloading.
- Added a contained original-image dialog and preview retry without saving another output file.
- Simplified controls to Name and Export with JPEG quality presets, PNG lossless output and persistent custom quality. Existing filename, format and quality inputs and defaults remain compatible.
- Preserve PNG alpha; reject JPEG alpha with a clear explanation. Validate portable filenames and avoid overwriting outputs when concurrent saves select the same counter.
- Report files already saved when a batch fails or is interrupted, and reject empty image tensors clearly.

Local Metadata Killer checks cover Classic and Nodes 2.0 on the recorded test environment. This update does not claim complete live acceptance of every node or cloud environment.

## 0.3.0 - development candidate - 2026-09-09

- Standardized eight public class IDs: `MATRIX_MetadataKiller`, `MATRIX_AutoPrompter`, `MATRIX_ImageBatchLoader`, `MATRIX_Resolution`, `MATRIX_AIInfluencerResolution`, `MATRIX_AIInfluencerResolution2K4K`, `MATRIX_EasyCrop`, and `MATRIX_SpectralSampler`.
- Kept the package at fourteen registered nodes; the eight old IDs are not registered as aliases.
- Added an offline workflow migration path that writes a separate copy and changes only the eight class IDs.
- Standardized the user-facing name as Auto Prompter.

This is a breaking workflow-identity change. Read [docs/migration.md](docs/migration.md) before opening 0.2.0 workflows with the new package.

## 0.2.0 - development candidate - 2026-09-09

- Unified the surviving execution and UI nodes into one package with six stable category directories.
- Preserved the public class IDs listed in `NODES.md` and retained `MATRIXLAB_EasyCrop`.
- Replaced the retired finishing pair with `MATRIX_PhotoFinisher`, a local deterministic Torch node with `Clean Digital`, `Everyday Capture`, and `Low Light` creative profiles.
- Set new Photo Finisher defaults to `Everyday Capture`, mix `1`, texture `1`, detail `1`, contrast `0`, warmth `0`, saturation `1`, and seed `42`.
- Simplified the general and AI-influencer resolution nodes to two integer outputs and included `MATRIXLAB_AIInfluencerResolution2K4K` for current Krea 2 geometry selection.
- Kept Auto Prompter provider generation behind an explicit paid action; ordinary graph execution returns saved text without a network request.
- Added public installation, migration, compatibility, node, license-notice, and agent-installation documentation.

Full live acceptance of the current bytes across both ComfyUI renderers and all model-dependent paths remains pending.

## 0.1.0

- Initial unified-package development metadata.
