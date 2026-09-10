# MATRIX Krea 2 — AI Influencer 4K (FP8), Version 1

After repository access is available, import
[the UI workflow](../examples/krea2-v1/MATRIX-Krea-2-AI-Influencer-4K-FP8-V1.ui.json).
The adjacent API JSON is for automated execution. Preserve the graph JSON separately:
Metadata Killer intentionally removes workflow metadata from saved images.

## Requirements

- Install this package and rgthree-comfy, then restart ComfyUI and reload the page.
- Tested numerical environment: RTX 5090, ComfyUI 0.33.3, PyTorch 2.8.0+cu128.
- Diffusion: `krea2_turbo_fp8_scaled.safetensors` under `models/diffusion_models`.
- Encoder: `qwen3vl_4b_bf16.safetensors` under `models/text_encoders`.
- VAE: `wan_2.1_vae.safetensors` under `models/vae`.
- Configure the [eye and skin detector assets and runtimes](detector-setup.md).
- LoRAs are optional. The Power Lora Loader intentionally contains no rows in the
  distributed workflow. If you choose to use a compatible Krea 2 LoRA, obtain it
  separately, confirm you are authorized to use it, and configure its strength and
  any required prompt trigger.
- Manual prompting is the saved default. Optional Auto Prompter use needs separate
  provider configuration; ordinary image generation does not make a provider request.

## Prompt and LoRA setup before queueing

The distributed workflow contains no scene, person, or character-specific generation
text. Its manual CLIP prompt is blank; fill it before queueing. Auto Prompter retains
the reusable instructions and system prompt, while `final_prompt` and
`character_trigger` are blank. Supply a character trigger only when the LoRA you add
requires one, and keep its spelling exact.

The skin-detail and eye-detail CLIP prompts remain populated because they are
functional instructions for those optional detail stages, not the primary scene or
identity prompt. Review them if you change those stages. The Power Lora Loader has no
rows, so the imported graph applies no LoRA until you add one.

## Use

Select 2K or 4K, enter the manual prompt or explicitly generate and review an Auto
Prompter result, add any intended LoRA rows, and then run. Skin and eye detail are
enabled; CameraLook is off and Renoise on. A valid empty eye detection/mask leaves
that region unchanged. Keep the model guard before the LoRA loader and use the
protected CLIP loader. Compatible diffusion LoRAs are supported; patches to protected
parameters or incompatible encoder hooks are rejected.

## Acceptance

The unchanged guard implementations completed six consecutive full 4K FP8 server
runs across compatible LoRA cases. Those historical runs used the original populated
V1 graph. The sanitized distributed default preserves its generation wiring while
intentionally clearing the primary prompts, character trigger, and LoRA rows, so it
does not reproduce the exact prompt and LoRA inputs used in those runs.

The historical V1 API graph additionally completed a full 3072x4096 run on that Pod
with the saver-only supplement: original PNG decoded, metadata verification passed,
and its 1024-pixel WebP preview decoded successfully. The original was visually
inspected. This does not claim an identical full-package installation was exercised on
the Pod. Package CI checks standalone imports, retained compatibility, and guard
contracts. See [GPU limits](krea2-gpu.md). Arbitrary LoRAs, other GPU/runtime versions,
and INT8 are not covered by this numerical acceptance. Frontend behavior and template
portability require their own verification; clean JSON is not proof of a tested
deployment template.
