# MATRIX LAB NODES

[![CI](https://github.com/JsonMatrixLab/MATRIX-LAB-Nodes/actions/workflows/ci.yml/badge.svg)](https://github.com/JsonMatrixLab/MATRIX-LAB-Nodes/actions/workflows/ci.yml)

Fourteen focused ComfyUI nodes for image input, resolution, sampling, masks, finishing, output, and assisted prompting—organized in six consistent `MATRIX LAB` categories.

> **Development candidate 0.2.0.** Read the current [compatibility and acceptance boundary](docs/compatibility.md) before using it in an important workflow.

## Installation

- **Install it yourself:** follow [INSTALL.md](INSTALL.md).
- **Ask a coding agent to install it:** provide the repository and require [AGENT-INSTALL.md](AGENT-INSTALL.md).

Install this unified pack as one folder under ComfyUI's `custom_nodes`. Do not enable it beside the older `MATRIXLAB-Nodes` or `MATRIXLAB-UI-Nodes` packs: retained class IDs would register twice. Back up workflows and review the [migration guide](docs/migration.md) before switching.

## Input & Output (2)

- [**MATRIX IMAGE BATCH LOADER**](docs/nodes/image-batch-loader.md) — load and reorder one to ten static input images while preserving each image's dimensions.
- [**MATRIX METADATA KILLER**](docs/nodes/matrix-save-clean.md) — save complete image batches as clean JPEG or PNG output without prompt or workflow metadata inputs.

## Resolution & Layout (3)

- [**MATRIX RESOLUTION**](docs/nodes/resolution.md) — calculate 1K, 2K, 4K, or exact custom pixel dimensions across common aspect ratios.
- [**MATRIX AI INFLUENCER RESOLUTION**](docs/nodes/ai-influencer-resolution.md) — select 1:1, 9:16, or 3:4 geometry at 1K, 2K, or 4K.
- [**MATRIX AI INFLUENCER RESOLUTION 2K/4K**](docs/nodes/ai-influencer-resolution-2k4k.md) — use the focused two-tier geometry selector required by current Krea 2 graphs.

Resolution nodes return integer geometry. They do not certify that a model supports the selected dimensions.

## Sampling & Detail (3)

- [**MATRIX SPECTRAL SAMPLER**](docs/nodes/spectral-sampler.md) — provide a native or spectral progressive ComfyUI sampler from explicit transform and scale controls.
- [**MATRIX LATENT TAIL**](docs/nodes/latent-tail.md) — run a short latent finishing pass, optionally restricted by a mask.
- [**MATRIX CROP TAIL PASTE**](docs/nodes/crop-tail-paste.md) — sample a small masked region at crop scale and paste it back into the source image.

## Masks & Detection (2)

- [**MATRIX SKIN MASK**](docs/nodes/skin-mask.md) — build selected human-part masks with an optional person gate and controlled edge finishing.
- [**MATRIX EYE MASK**](docs/nodes/eye-mask.md) — detect eye boxes and optionally refine them into individual and union masks with SAM.

Model weights are not bundled or downloaded. Both mask nodes require separately acquired, hash-matched assets and compatible runtimes; follow [detector and segmentation setup](docs/detector-setup.md).

## Image Processing (3)

- [**MATRIX PHOTO FINISHER**](docs/nodes/photo-finisher.md) — apply deterministic local tone, color, detail, and texture with profile, trim, seed, and optional mask controls.
- [**MATRIX EASY CROP**](docs/nodes/easy-crop.md) — crop one static ComfyUI input image through visible normalized geometry and return its alpha-derived mask.
- [**MATRIX OUTPUT STAGE**](docs/nodes/output-stage.md) — resolve an image toward explicit target dimensions through connected model, sampling, VAE, and optional upscale inputs.

Try Photo Finisher without a model or provider using the [included example workflow](examples/README.md).

## Prompting (1)

- [**MATRIX AUTO PROMPTER**](docs/nodes/auto-prompter.md) — return an editable saved prompt locally, with an explicit action for assisted prompting from ordered reference images.

Ordinary graph execution makes no provider request. **Generate Prompt** sends the selected reference images and prompt fields to xAI only after credential setup and explicit paid-use intent; provider charges may apply. Credentials stay outside serialized workflows.

## Package boundary

The installed `MANIFEST.json` is the machine-readable inventory for the exact artifact. Offline CI checks package registration, public schemas, assets, and syntax; complete live renderer, GPU, model, and workflow acceptance remains a separate release gate.

## License

MATRIX LAB code is distributed under the repository's [proprietary license](LICENSE). The bundled Cascadia Mono font has its own [SIL Open Font License 1.1](web/assets/CascadiaMono-LICENSE.txt).
