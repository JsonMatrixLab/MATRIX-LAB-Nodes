# MATRIX Krea 2 — AI Influencer 4K (FP8), Version 1

After repository access is available, import
[the UI workflow](../examples/krea2-v1/MATRIX-Krea-2-AI-Influencer-4K-FP8-V1.ui.json).
The adjacent API JSON is for automated execution. Preserve the graph JSON separately:
Metadata Killer intentionally removes workflow metadata from saved images.

## Requirements

- Install exact node package 0.4.0 and rgthree-comfy, then restart ComfyUI and reload
  the page. Use a workflow release that has migrated its finishing stage to Photo
  Finisher.
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
enabled, and Photo Finisher owns the photographic finishing stage. A valid empty eye
detection/mask leaves that region unchanged. Keep the model guard before the LoRA loader and use the
protected CLIP loader. Compatible diffusion LoRAs are supported; patches to protected
parameters or incompatible encoder hooks are rejected.

## Acceptance

Node package 0.4.0 targets the four schema-compatible V1 aliases and their current
IDs with the unified green frontend. On the exact installed package, all 20 MATRIX
IDs resolved to that pack in ComfyUI Classic. The workflow was saved on the Pod,
loaded in a fresh browser, and exported with exact equality to the supplied API
graph.

The release workflow completed three RTX 5090 FP8 runs: 2K with Photo Finisher ON,
2K with it OFF, and 4K with it ON. The environment was ComfyUI 0.33.3 at core
`4da9e2dbead52fc1e68beae33fe3d7ad63b63241`, frontend 1.49.6, and PyTorch
2.8.0+cu128. Tests used a standard manual prompt without a LoRA. The optional Auto
Prompter provider action was not run.

Package CI separately checks imports, retained aliases, and guard contracts. See
[GPU limits](krea2-gpu.md). Arbitrary LoRAs, other GPU/runtime versions, INT8,
provider behavior, and Nodes 2.0 are outside this acceptance.
