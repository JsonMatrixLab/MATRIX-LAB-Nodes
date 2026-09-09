# Node reference

Package version 0.2.0 contains the fourteen classes below in six `MATRIX LAB` groups. The installed `MANIFEST.json` is authoritative for a particular artifact.

| Display name | Class ID | Inputs | Outputs | Guide |
| --- | --- | --- | --- | --- |
| MATRIX METADATA KILLER | `MATRIX_SaveClean` | `images`; save options | output node | [Guide](docs/nodes/matrix-save-clean.md) |
| MATRIX IMAGE BATCH LOADER | `MATRIXLAB_ImageBatchLoader` | `collection` | `images`, `masks` | [Guide](docs/nodes/image-batch-loader.md) |
| MATRIX RESOLUTION | `MATRIXLAB_Resolution` | ratio, tier, custom dimensions | `width`, `height` | [Guide](docs/nodes/resolution.md) |
| MATRIX AI INFLUENCER RESOLUTION | `MATRIXLAB_AIInfluencerResolution` | ratio, tier | `width`, `height` | [Guide](docs/nodes/ai-influencer-resolution.md) |
| MATRIX AI INFLUENCER RESOLUTION 2K/4K | `MATRIXLAB_AIInfluencerResolution2K4K` | ratio, 2K/4K tier | `width`, `height` | [Guide](docs/nodes/ai-influencer-resolution-2k4k.md) |
| MATRIX SPECTRAL SAMPLER | `MATRIXSpectralSampler` | sampler and spectral controls | `sampler` | [Guide](docs/nodes/spectral-sampler.md) |
| MATRIX LATENT TAIL | `MATRIX_LatentTail` | model/noise/conditioning/latent; tail controls | `latent` | [Guide](docs/nodes/latent-tail.md) |
| MATRIX CROP TAIL PASTE | `MATRIX_CropTailPaste` | image/mask/model/noise/conditioning/VAE; crop controls | `image` | [Guide](docs/nodes/crop-tail-paste.md) |
| MATRIX SKIN MASK | `MATRIX_SkinMask` | image; part and mask controls | `mask`, `preview` | [Guide](docs/nodes/skin-mask.md) |
| MATRIX EYE MASK | `MATRIX_EyeMask` | image; detector and mask controls | `mask`, `masks`, `bboxes`, `preview` | [Guide](docs/nodes/eye-mask.md) |
| MATRIX PHOTO FINISHER | `MATRIX_PhotoFinisher` | image; optional mask and finish controls | `image` | [Guide](docs/nodes/photo-finisher.md) |
| MATRIX EASY CROP | `MATRIXLAB_EasyCrop` | uploaded image and crop geometry | `image`, `mask` | [Guide](docs/nodes/easy-crop.md) |
| MATRIX OUTPUT STAGE | `MATRIX_OutputStage` | image/model/noise/conditioning/VAE/target geometry; output controls | `image`, `info` | [Guide](docs/nodes/output-stage.md) |
| MATRIX AUTO PROMPTER | `MATRIXLAB_PromptDirector` | saved prompt fields; optional images | `prompt` | [Guide](docs/nodes/auto-prompter.md) |

`MATRIXLAB_AIInfluencerResolution2K4K` does not replace the base AI Influencer Resolution class.
