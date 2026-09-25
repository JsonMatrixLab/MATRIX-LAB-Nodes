# MATRIX LAB NODES

[![CI](https://github.com/JsonMatrixLab/MATRIX-LAB-Nodes/actions/workflows/ci.yml/badge.svg)](https://github.com/JsonMatrixLab/MATRIX-LAB-Nodes/actions/workflows/ci.yml)

Sixteen current ComfyUI nodes for image input, resolution, sampling, masks, finishing,
output, and assisted prompting, plus four schema-compatible Krea 2 V1 aliases. All
20 registered class IDs remain in six consistent `MATRIX LAB` categories.

> **Package version 0.4.0.** Photo Finisher is now the only MATRIX photographic
> finishing implementation. The four schema-compatible Krea 2 V1 aliases retain the
> source-owned green frontend repair introduced in 0.3.5. Read the current
> [compatibility and acceptance boundary](docs/compatibility.md) before using it in an
> important workflow.

## MATRIX Krea 2 — AI Influencer 4K (FP8)

Use the included
[V1 workflow](examples/krea2-v1/MATRIX-Krea-2-AI-Influencer-4K-FP8-V1.ui.json) with
its [setup and verified scope](docs/krea2-v1.md). The package includes
`MATRIX_Krea2CLIPLoader`, `MATRIX_Krea2ModelGuard`, the current Metadata Killer,
and safe handling of valid empty eye masks. Text encoding and diffusion remain on
GPU. The current RTX 5090 FP8 acceptance is documented in the
[GPU guard notes](docs/krea2-gpu.md); INT8 is outside that acceptance.

V1 compatibility aliases preserve the saved Spectral, resolution, prompt, and
image-loader identities. The former two-node finishing chain requires deliberate
replacement with Photo Finisher; see the [migration guide](docs/migration.md).

## Installation

- **Install it yourself:** follow [INSTALL.md](INSTALL.md).
- **Ask a coding agent to install it:** provide the repository and require [AGENT-INSTALL.md](AGENT-INSTALL.md).

Install this unified pack as one folder under ComfyUI's `custom_nodes`. Do not enable
it beside `matrix-krea2-adapter`, the older `MATRIXLAB-Nodes` or
`MATRIXLAB-UI-Nodes` split packs, or a standalone Metadata Killer: registrations or
frontend targeting overlap. Preserve existing packs and workflows, obtain authority
before disabling them recoverably, and review the [migration guide](docs/migration.md)
before switching.

## Input & Output (3 current)

- [**MATRIX IMAGE BATCH LOADER**](docs/nodes/image-batch-loader.md) — load and reorder one to ten static input images while preserving each image's dimensions.
- [**MATRIX METADATA KILLER**](docs/nodes/metadata-killer.md) — save complete image batches as clean JPEG or PNG output without prompt or workflow metadata inputs.
- [**MATRIX VIDEO METADATA KILLER**](docs/nodes/video-metadata-killer.md) — remux MP4 video/audio into a newly saved native VIDEO while removing descriptive container and stream tags.

## Resolution & Layout (3 current)

- [**MATRIX RESOLUTION**](docs/nodes/resolution.md) — calculate 1K, 2K, 4K, or exact custom pixel dimensions across common aspect ratios.
- [**MATRIX AI INFLUENCER RESOLUTION**](docs/nodes/ai-influencer-resolution.md) — select 1:1, 9:16, or 3:4 geometry at 1K, 2K, or 4K.
- [**MATRIX AI INFLUENCER RESOLUTION 2K/4K**](docs/nodes/ai-influencer-resolution-2k4k.md) — use the focused two-tier geometry selector required by current Krea 2 graphs.

Resolution nodes return integer geometry. They do not certify that a model supports the selected dimensions.

## Sampling & Detail (4 current)

- [**MATRIX SPECTRAL SAMPLER**](docs/nodes/spectral-sampler.md) — provide a native or spectral progressive ComfyUI sampler from explicit transform and scale controls.
- [**MATRIX LATENT TAIL**](docs/nodes/latent-tail.md) — run a short latent finishing pass, optionally restricted by a mask.
- [**MATRIX CROP TAIL PASTE**](docs/nodes/crop-tail-paste.md) — sample a small masked region at crop scale and paste it back into the source image.
- **MATRIX KREA2 MODEL GUARD** — protect the observed Krea 2 FP8 diffusion-model corruption boundary before compatible LoRAs; see the [GPU guard notes](docs/krea2-gpu.md).

## Masks & Detection (2 current)

- [**MATRIX SKIN MASK**](docs/nodes/skin-mask.md) — build selected human-part masks with an optional person gate and controlled edge finishing.
- [**MATRIX EYE MASK**](docs/nodes/eye-mask.md) — detect eye boxes and optionally refine them into individual and union masks with SAM.

Model weights are not bundled or downloaded. Both mask nodes require separately acquired, hash-matched assets and compatible runtimes; follow [detector and segmentation setup](docs/detector-setup.md).

## Image Processing (3 current)

- [**MATRIX PHOTO FINISHER**](docs/nodes/photo-finisher.md) — apply deterministic local tone, color, detail, and texture with profile, trim, seed, and optional mask controls.
- [**MATRIX EASY CROP**](docs/nodes/easy-crop.md) — crop one static ComfyUI input image through visible normalized geometry and return its alpha-derived mask.
- [**MATRIX OUTPUT STAGE**](docs/nodes/output-stage.md) — resolve an image toward explicit target dimensions through connected model, sampling, VAE, and optional upscale inputs.

Try Photo Finisher without a model or provider using the [included example workflow](examples/README.md).

## Prompting (3 current)

- [**MATRIX AUTO PROMPTER**](docs/nodes/auto-prompter.md) — return an editable saved prompt locally, with an explicit action for assisted prompting from ordered reference images.
- **MATRIX KREA2 CLIP LOADER** — load the protected Qwen3-VL 4B Krea 2 text encoder for GPU text encoding; see the [GPU guard notes](docs/krea2-gpu.md).
- [**MATRIX PROMPT**](docs/nodes/prompt.md) — preserve one editable multiline prompt exactly, without AI or provider behavior.

Ordinary graph execution makes no provider request. **Generate Prompt** sends the selected reference images and prompt fields to xAI only after credential setup and explicit paid-use intent; provider charges may apply. Credentials stay outside serialized workflows.

## Krea 2 V1 compatibility aliases (4)

Four aliases preserve schema-compatible V1 graph identities:
`MATRIXSpectralSampler`, `MATRIXLAB_AIInfluencerResolution2K4K`,
`MATRIXLAB_ImageBatchLoader`, and `MATRIXLAB_PromptDirector`. These registrations
are included in the 20-ID manifest; they do not add categories or replace the
current IDs. See [NODES.md](NODES.md) for the exact mapping.

Version 0.4.0 targets both the current and aliased IDs in the unified frontend. The
exact package was verified in ComfyUI Classic 0.33.3 with frontend 1.49.6 on an RTX
5090: all 20 IDs loaded from the unified pack, the workflow survived save and fresh
browser reload, and its frontend export exactly matched the API graph. Nodes 2.0 is
not a supported or verified target for this release.

## Package boundary

The installed `MANIFEST.json` is the machine-readable inventory for the exact
artifact. The bundled Krea 2 workflow completed 2K with Photo Finisher enabled, 2K
with it bypassed, and 4K with it enabled on the recorded Classic/RTX 5090 boundary.
Those runs used a standard manual prompt without a LoRA; the optional Auto Prompter
provider action was not run. Other hosts, models, LoRAs, provider behavior, and image
quality choices require their own evaluation.

## License

Access to the repository or an archive does not grant permission beyond the
repository's [proprietary license](LICENSE). The bundled Cascadia Mono font has its
own [SIL Open Font License 1.1](web/assets/CascadiaMono-LICENSE.txt).
