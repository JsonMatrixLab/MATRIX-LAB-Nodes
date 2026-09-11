# Changelog

User-visible changes are recorded here. This file describes package content; publication tags and release channels are separate facts.

## 0.4.0 - Photo Finisher replacement - 2026-09-11

- Remove the Camera Look and Renoise registrations and runtime implementations.
- Keep Photo Finisher as the single MATRIX photographic-finishing node.
- Preserve all 16 current nodes and the four schema-compatible V1 aliases, for 20
  registered IDs across the existing six groups.
- Preserve the 0.3.5 frontend targeting repair for those four aliases.
- Require manual replacement and retuning for workflows that used the removed
  finishing nodes; their old controls have no exact Photo Finisher mapping.

Verified the exact package in ComfyUI Classic 0.33.3/frontend 1.49.6 on an RTX 5090:
20 unified IDs, save and fresh-browser reload, exact frontend/API graph equality, and
successful 2K Photo Finisher ON, 2K OFF, and 4K ON runs. These used a standard manual
prompt without a LoRA; the optional provider action was not run. Nodes 2.0 is not a
supported or verified target for this release.

## 0.3.5 - legacy/current frontend compatibility - 2026-09-10

- Target the four Krea 2 V1 aliases and their current IDs with the same unified green
  frontend controls for Spectral Sampler, AI Influencer Resolution 2K/4K, Image
  Batch Loader, and Auto Prompter.
- Accept both legacy and current Image Batch Loader IDs in the Auto Prompter frontend
  image-source check.
- Keep the 22 registered backend IDs, schemas, processing code, GPU guards, and
  sanitized examples unchanged from 0.3.4.

Offline source and package checks do not establish live Classic, Nodes 2.0, GPU, or
workflow acceptance for this candidate.

## 0.3.4 - packaging hygiene - 2026-09-10

- Align release documentation and manifest checks with the 22 registered IDs: 16
  current nodes, CameraLook and Renoise compatibility classes, and four V1 aliases
  across the existing six groups.
- Prepare the Krea 2 V1 examples without a private scene prompt, character trigger,
  selected LoRA, or Power Lora Loader rows while retaining the reusable Auto
  Prompter instructions/system prompt and functional skin/eye detail prompts.
- Document private-repository access conditionally and keep the proprietary license
  boundary explicit.

Runtime behavior is unchanged from 0.3.3.

## 0.3.3 - Krea2 FP8 V1 compatibility - 2026-09-10

- Add GPU CLIP and static diffusion model guards for the observed Krea2 resident-weight corruption.
- Preserve native CUDA computation and reject incompatible protected-parameter patches.
- Skip valid empty SAM eye masks rather than failing the whole workflow.
- Restore narrowly scoped Krea2 V1 node identities and the original CameraLook/Renoise algorithms.
- Include the MATRIX Krea 2 — AI Influencer 4K (FP8) V1 workflow with the current Metadata Killer.
- Document the tested FP8 runtime, setup, optional LoRAs and separate frontend/template acceptance limits.

## 0.3.2 - development candidate - 2026-09-09

- Refresh Eye Mask SAM embeddings when the input image changes or its pixels are modified in place. Preserve reuse for repeated refinement of the same unchanged image.
- Prevent Python object-identity reuse from selecting a previous image's embedding.

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

At that development point, full live renderer and model-path acceptance had not yet
been completed.

## 0.1.0

- Initial unified-package development metadata.
