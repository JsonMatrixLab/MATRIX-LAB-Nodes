# Node reference

Package version 0.4.0 registers 20 class IDs in six `MATRIX LAB` groups: 16
current nodes and four schema-compatible aliases. The installed `MANIFEST.json` is
authoritative for a particular artifact.

| Group | Status | Display name | Class ID | Inputs | Outputs | Guide |
| --- | --- | --- | --- | --- | --- | --- |
| Input & Output | Current | MATRIX METADATA KILLER | `MATRIX_MetadataKiller` | `images`; save options | output node | [Guide](docs/nodes/metadata-killer.md) |
| Input & Output | Current | MATRIX IMAGE BATCH LOADER | `MATRIX_ImageBatchLoader` | `collection` | `images`, `masks` | [Guide](docs/nodes/image-batch-loader.md) |
| Resolution & Layout | Current | MATRIX RESOLUTION | `MATRIX_Resolution` | ratio, tier, custom dimensions | `width`, `height` | [Guide](docs/nodes/resolution.md) |
| Resolution & Layout | Current | MATRIX AI INFLUENCER RESOLUTION | `MATRIX_AIInfluencerResolution` | ratio, tier | `width`, `height` | [Guide](docs/nodes/ai-influencer-resolution.md) |
| Resolution & Layout | Current | MATRIX AI INFLUENCER RESOLUTION 2K/4K | `MATRIX_AIInfluencerResolution2K4K` | ratio, 2K/4K tier | `width`, `height` | [Guide](docs/nodes/ai-influencer-resolution-2k4k.md) |
| Sampling & Detail | Current | MATRIX SPECTRAL SAMPLER | `MATRIX_SpectralSampler` | sampler and spectral controls | `sampler` | [Guide](docs/nodes/spectral-sampler.md) |
| Sampling & Detail | Current | MATRIX LATENT TAIL | `MATRIX_LatentTail` | model/noise/conditioning/latent; tail controls | `latent` | [Guide](docs/nodes/latent-tail.md) |
| Sampling & Detail | Current | MATRIX CROP TAIL PASTE | `MATRIX_CropTailPaste` | image/mask/model/noise/conditioning/VAE; crop controls | `image` | [Guide](docs/nodes/crop-tail-paste.md) |
| Sampling & Detail | Current | MATRIX KREA2 MODEL GUARD | `MATRIX_Krea2ModelGuard` | FP8 Krea 2 `model` before LoRAs | `MODEL` | [Guide](docs/krea2-gpu.md) |
| Masks & Detection | Current | MATRIX SKIN MASK | `MATRIX_SkinMask` | image; part and mask controls | `mask`, `preview` | [Guide](docs/nodes/skin-mask.md) |
| Masks & Detection | Current | MATRIX EYE MASK | `MATRIX_EyeMask` | image; detector and mask controls | `mask`, `masks`, `bboxes`, `preview` | [Guide](docs/nodes/eye-mask.md) |
| Image Processing | Current | MATRIX PHOTO FINISHER | `MATRIX_PhotoFinisher` | image; optional mask and finish controls | `image` | [Guide](docs/nodes/photo-finisher.md) |
| Image Processing | Current | MATRIX EASY CROP | `MATRIX_EasyCrop` | uploaded image and crop geometry | `image`, `mask` | [Guide](docs/nodes/easy-crop.md) |
| Image Processing | Current | MATRIX OUTPUT STAGE | `MATRIX_OutputStage` | image/model/noise/conditioning/VAE/target geometry; output controls | `image`, `info` | [Guide](docs/nodes/output-stage.md) |
| Prompting | Current | MATRIX AUTO PROMPTER | `MATRIX_AutoPrompter` | saved prompt fields; optional images | `prompt` | [Guide](docs/nodes/auto-prompter.md) |
| Prompting | Current | MATRIX KREA2 CLIP LOADER | `MATRIX_Krea2CLIPLoader` | Krea 2 Qwen3-VL 4B `clip_name` | `CLIP` | [Guide](docs/krea2-gpu.md) |
| Sampling & Detail | V1 alias | MATRIX SPECTRAL SAMPLER | `MATRIXSpectralSampler` | same as `MATRIX_SpectralSampler` | `sampler` | [Migration](docs/migration.md) |
| Resolution & Layout | V1 alias | MATRIX AI INFLUENCER RESOLUTION 2K/4K | `MATRIXLAB_AIInfluencerResolution2K4K` | same as `MATRIX_AIInfluencerResolution2K4K` | `width`, `height` | [Migration](docs/migration.md) |
| Input & Output | V1 alias | MATRIX IMAGE BATCH LOADER | `MATRIXLAB_ImageBatchLoader` | same as `MATRIX_ImageBatchLoader` | `images`, `masks` | [Migration](docs/migration.md) |
| Prompting | V1 alias | MATRIX AUTO PROMPTER | `MATRIXLAB_PromptDirector` | same as `MATRIX_AutoPrompter` | `prompt` | [Migration](docs/migration.md) |

`MATRIX_AIInfluencerResolution2K4K` does not replace the base AI Influencer Resolution class.
Compatibility aliases preserve serialized V1 identities; new workflows should use the
current class IDs. They do not represent additional implementations.

Version 0.4.0 targets each legacy alias and its current ID with the same unified
green frontend. Both ID sets were verified in ComfyUI Classic with the exact release
workflow. Nodes 2.0 is not supported or verified for this release.
