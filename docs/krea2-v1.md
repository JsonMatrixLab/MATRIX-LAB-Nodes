# MATRIX Krea 2 — AI Influencer 4K (FP8), Version 1

Import [the UI workflow](../examples/krea2-v1/MATRIX-Krea-2-AI-Influencer-4K-FP8-V1.ui.json).
The adjacent API JSON is for automated execution. Preserve the graph JSON separately:
Metadata Killer intentionally removes workflow metadata from saved images.

## Requirements

- Install this repository and rgthree-comfy, then restart ComfyUI and reload the page.
- Tested numerical environment: RTX 5090, ComfyUI 0.33.3, PyTorch 2.8.0+cu128.
- Diffusion: `krea2_turbo_fp8_scaled.safetensors` under `models/diffusion_models`.
- Encoder: `qwen3vl_4b_bf16.safetensors` under `models/text_encoders`.
- VAE: `wan_2.1_vae.safetensors` under `models/vae`.
- Configure the [eye and skin detector assets and runtimes](detector-setup.md).
- Obtain compatible Krea2 LoRAs separately. The saved graph selects `4shl3y.safetensors`;
  replace it with an available compatible character LoRA and update its prompt trigger,
  or disable that LoRA for an unconditioned character. Model/LoRA files are not bundled.
- Manual prompting is the saved default. Optional Auto Prompter needs separate provider
  configuration; ordinary image generation does not make a new provider request.

## Use

Select 2K or 4K, edit the manual prompt, set the LoRA and run. Skin and eye detail
are enabled; CameraLook is off and Renoise on. A valid empty eye detection/mask
leaves that region unchanged. Keep the model guard before the LoRA loader and use
the protected CLIP loader. Compatible diffusion LoRAs are supported; patches to
protected parameters or incompatible encoder hooks are rejected.

## Acceptance

The unchanged guard implementations completed six consecutive full 4K FP8 server
runs with Nicegirls, Skindetails, RawGirl 1.0 and character returns. The V1 graph
preserves that generation path and replaces only the saver with the current
Metadata Killer. The exact V1 API graph additionally completed a full 3072x4096
run on that Pod with the saver-only supplement: original PNG decoded, metadata
verification passed, and its 1024-pixel WebP preview decoded successfully. The
original was visually inspected. This does not claim an identical full-package
installation was exercised on the Pod. Package CI checks standalone imports, retained compatibility and
guard contracts. See [GPU limits](krea2-gpu.md). Arbitrary LoRAs, other GPU/runtime
versions and INT8 are not covered by this numerical acceptance. Frontend behavior
and template portability require their own verification; a clean JSON is not proof
of a tested deployment template.
