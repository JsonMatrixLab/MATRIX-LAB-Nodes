# MATRIX LAB NODES

[![CI](https://github.com/JsonMatrixLab/MATRIX-LAB-Nodes/actions/workflows/ci.yml/badge.svg)](https://github.com/JsonMatrixLab/MATRIX-LAB-Nodes/actions/workflows/ci.yml)

Sixteen current ComfyUI nodes for image input, resolution, sampling, masks, finishing,
output, and assisted prompting, plus six narrowly scoped Krea 2 V1 compatibility
registrations. All 22 registered class IDs remain in six consistent `MATRIX LAB`
categories.

> **Package version 0.3.4.** This patch changes packaging and example hygiene;
> runtime behavior is unchanged from 0.3.3. Read the current
> [compatibility and acceptance boundary](docs/compatibility.md) before using it in an
> important workflow.

## MATRIX Krea 2 — AI Influencer 4K (FP8)

After repository access is available, use the
[V1 workflow](examples/krea2-v1/MATRIX-Krea-2-AI-Influencer-4K-FP8-V1.ui.json) with
its [setup and verified scope](docs/krea2-v1.md). The package includes
`MATRIX_Krea2CLIPLoader`, `MATRIX_Krea2ModelGuard`, the current Metadata Killer,
and safe handling of valid empty eye masks. Text encoding and diffusion remain on
GPU. The original six-case RTX 5090 FP8 numerical acceptance is documented in the
[GPU guard notes](docs/krea2-gpu.md); INT8 is outside that acceptance.

V1 compatibility registrations preserve the saved Spectral, resolution, prompt,
image-loader, CameraLook, and Renoise identities. Photo Finisher remains available
for new workflows and is not substituted for V1 finishing settings. See the
[migration guide](docs/migration.md).

## Installation

- **Install it yourself:** follow [INSTALL.md](INSTALL.md).
- **Ask a coding agent to install it:** provide the repository and require [AGENT-INSTALL.md](AGENT-INSTALL.md).

Install this unified pack as one folder under ComfyUI's `custom_nodes`. Do not enable it beside the older `MATRIXLAB-Nodes` or `MATRIXLAB-UI-Nodes` packs: retained class IDs would register twice. Back up workflows and review the [migration guide](docs/migration.md) before switching.

## Input & Output (2 current)

- [**MATRIX IMAGE BATCH LOADER**](docs/nodes/image-batch-loader.md) — load and reorder one to ten static input images while preserving each image's dimensions.
- [**MATRIX METADATA KILLER**](docs/nodes/metadata-killer.md) — save complete image batches as clean JPEG or PNG output without prompt or workflow metadata inputs.

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

## Prompting (2 current)

- [**MATRIX AUTO PROMPTER**](docs/nodes/auto-prompter.md) — return an editable saved prompt locally, with an explicit action for assisted prompting from ordered reference images.
- **MATRIX KREA2 CLIP LOADER** — load the protected Qwen3-VL 4B Krea 2 text encoder for GPU text encoding; see the [GPU guard notes](docs/krea2-gpu.md).

Ordinary graph execution makes no provider request. **Generate Prompt** sends the selected reference images and prompt fields to xAI only after credential setup and explicit paid-use intent; provider charges may apply. Credentials stay outside serialized workflows.

## Krea 2 V1 compatibility registrations (6)

`MATRIX_CameraLook` and `MATRIX_Renoise` retain their original implementations and
saved controls in Image Processing. Four aliases preserve V1 graph identities:
`MATRIXSpectralSampler`, `MATRIXLAB_AIInfluencerResolution2K4K`,
`MATRIXLAB_ImageBatchLoader`, and `MATRIXLAB_PromptDirector`. These registrations
are included in the 22-ID manifest; they do not add categories or replace the
current IDs. See [NODES.md](NODES.md) for the exact mapping.

## Package boundary

The installed `MANIFEST.json` is the machine-readable inventory for the exact artifact. Offline CI checks package registration, public schemas, assets, and syntax; complete live renderer, GPU, model, and workflow acceptance remains a separate release gate.

## License

Access to the repository or an archive does not grant permission beyond the
repository's [proprietary license](LICENSE). The bundled Cascadia Mono font has its
own [SIL Open Font License 1.1](web/assets/CascadiaMono-LICENSE.txt).
