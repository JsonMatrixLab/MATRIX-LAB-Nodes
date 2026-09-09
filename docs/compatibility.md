# Compatibility

## Current status

Version 0.3.0 is a development candidate. Offline checks cover package registration, schemas, category layout, deterministic builds, runtime registry integrity, and frontend syntax. Those checks do not establish complete live acceptance for Classic and Nodes 2.0 renderers, every interaction, every GPU/model combination, or production use.

| Area | Current boundary |
| --- | --- |
| Python | Package metadata requires Python 3.10 or newer. |
| ComfyUI frontend | Shared presentation targets Classic and Nodes 2.0; current exact-build full interaction acceptance remains pending. Native widgets remain the serialized execution state. |
| Torch/CUDA | Uses the host ComfyUI stack. No universal hardware, Torch, or CUDA matrix is claimed. |
| Resolution nodes | Model-independent integer geometry; output dimensions do not certify that a model can generate or process that size. |
| Image processing | Photo Finisher is local Torch processing. Easy Crop and Image Batch Loader operate on static uploaded images. |
| Skin Mask | Needs separately acquired, licensed, and configured segmentation assets plus compatible runtimes. Installation does not complete this setup. An all-parts-off run can return an empty mask without inference. |
| Eye Mask | Needs the registered eye detector and, when enabled, SAM refinement assets/runtime. Model weights are not bundled; installation does not complete this setup. |
| Sampling/detail | Requires compatible ComfyUI MODEL, NOISE, CONDITIONING, LATENT, VAE, SAMPLER, or UPSCALE_MODEL inputs as documented per node. Sampler availability follows the host ComfyUI contract. |
| Auto Prompter | Ordinary graph execution is local. Explicit Generate Prompt requires a supported xAI credential/model and may be paid. |
| Platforms | No broad Windows, Linux, macOS, cloud, or portable-build support claim is made until each environment is accepted with the exact release bytes. |

## External assets

The distribution contains logical names and hashes for required runtime assets but no model weights. A matching filename alone is insufficient. Missing, unregistered, or hash-mismatched assets must fail rather than silently selecting another model. Follow [detector and segmentation setup](detector-setup.md) for exact paths, sources, hashes, runtime requirements, and the license evidence currently available for each asset.

## Workflow compatibility

Stable class IDs help existing workflows locate retained nodes; they do not guarantee that older widget or output positions remain compatible. Read [migration.md](migration.md) for the finishing and resolution changes. Keep a rollback copy and validate duplicate workflows before production use.
