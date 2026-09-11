# Compatibility

## Current status

Version 0.4.0 passed package registration, schema, deterministic-build, registry, and
frontend checks. The exact package also completed its bundled Krea 2 workflow on the
recorded Classic/RTX 5090 boundary. This is a tested compatibility boundary rather
than a universal hardware or workflow guarantee.

| Area | Current boundary |
| --- | --- |
| Python | Package metadata requires Python 3.10 or newer. |
| ComfyUI frontend | Classic frontend 1.49.6 was verified through workflow save, fresh-browser load, 20 unified node providers, and exact frontend/API graph equality. Nodes 2.0 is not supported or verified for this release. |
| Torch/CUDA | Verified with ComfyUI 0.33.3, core `4da9e2dbead52fc1e68beae33fe3d7ad63b63241`, PyTorch 2.8.0+cu128, and an RTX 5090. No universal hardware, Torch, or CUDA matrix is claimed. |
| Resolution nodes | Model-independent integer geometry; output dimensions do not certify that a model can generate or process that size. |
| Image processing | Photo Finisher is local Torch processing. Easy Crop and Image Batch Loader operate on static uploaded images. |
| Skin Mask | Needs separately acquired, licensed, and configured segmentation assets plus compatible runtimes. Installation does not complete this setup. An all-parts-off run can return an empty mask without inference. |
| Eye Mask | Needs the registered eye detector and, when enabled, SAM refinement assets/runtime. Model weights are not bundled; installation does not complete this setup. |
| Sampling/detail | Requires compatible ComfyUI MODEL, NOISE, CONDITIONING, LATENT, VAE, SAMPLER, or UPSCALE_MODEL inputs as documented per node. Sampler availability follows the host ComfyUI contract. |
| Auto Prompter | Ordinary graph execution is local. Explicit Generate Prompt requires a supported xAI credential/model and may be paid. |
| Workflow execution | The bundled Krea 2 graph completed 2K with Photo Finisher ON, 2K with it OFF, and 4K with it ON. Tests used a standard manual prompt without a LoRA. The optional Auto Prompter provider action was not run. |
| Platforms | The verified environment is the recorded Linux GPU Pod. Other operating systems, cloud images, and portable builds require their own acceptance. |

## External assets

The distribution contains logical names and hashes for required runtime assets but no model weights. A matching filename alone is insufficient. Missing, unregistered, or hash-mismatched assets must fail rather than silently selecting another model. Follow [detector and segmentation setup](detector-setup.md) for exact paths, sources, hashes, runtime requirements, and the license evidence currently available for each asset.

## Workflow compatibility

Stable class IDs help existing workflows locate retained nodes; they do not guarantee that older widget or output positions remain compatible. Camera Look and Renoise are no longer registered; replace their chain with Photo Finisher and retune it. Read [migration.md](migration.md) for the finishing and resolution changes. Keep a rollback copy and validate duplicate workflows before production use.
