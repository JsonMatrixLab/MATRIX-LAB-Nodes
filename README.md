# MATRIX LAB NODES

A unified ComfyUI custom-node pack with 14 nodes in six functional groups. Development version 0.1.0.

| Group | Nodes |
| --- | --- |
| [Input & Output](nodes/input_output/) | MATRIX METADATA KILLER, MATRIX IMAGE BATCH LOADER |
| [Resolution & Layout](nodes/resolution_layout/) | MATRIX RESOLUTION, MATRIX AI INFLUENCER RESOLUTION |
| [Sampling & Detail](nodes/sampling_detail/) | MATRIX SPECTRAL SAMPLER, MATRIX LATENT TAIL, MATRIX CROP TAIL PASTE |
| [Masks & Detection](nodes/masks_detection/) | MATRIX SKIN MASK, MATRIX EYE MASK |
| [Image Processing](nodes/image_processing/) | MATRIX RENOISE, MATRIX CAMERA LOOK, MATRIX EASY CROP, MATRIX OUTPUT STAGE |
| [Prompting](nodes/prompting/) | MATRIX AUTO PROMPTER |

## Installation

Install this repository under your ComfyUI custom_nodes directory and install requirements.txt using ComfyUI's Python environment, then restart ComfyUI.

This pack preserves class IDs from MATRIXLAB-Nodes and MATRIXLAB-UI-Nodes. Disable those two older packs before enabling this one. Installing them together produces duplicate class registrations. Keep a backup of your workflows and previous installation before switching.

The nodes use ComfyUI's existing torch installation; keep a torch build appropriate for your hardware. Detection and segmentation nodes also require their external model/provider dependencies. Eye Mask validates the model identities listed in _core/runtime-assets.json; model weights are not bundled. Provider-backed prompting requires a configured credential and an explicit generation action.

## Resolution

Both Resolution controls output only width and height. 1K, 2K and 4K mean an exact longer edge of 1024, 2048 and 4096 pixels. The shorter edge follows the selected aspect ratio, rounded to the nearest integer. These are pixel dimensions, not a guarantee that a model supports direct generation at that size.

General Resolution offers eight aspect presets plus Custom, with exact custom dimensions from 1 to 16384 pixels, Swap and Reset. AI Influencer Resolution offers 1:1, 9:16 and 3:4.

Old general Resolution workflows preserve their previous pixel dimensions as Custom where safe. Old connected AI Influencer nodes used a six-output render/delivery/sampler contract and require manual replacement; they are marked as legacy missing nodes instead of silently rewiring incompatible outputs. Review generation size, delivery size and sampler settings separately.

Resolution Plan, Resolution 2K and Resolution 4K Progressive are not included. Workflows using those classes require migration.

## Compatibility and status

The UI supports Classic and Nodes 2.0 through the shared MATRIX presentation. Offline geometry, serialization, lifecycle and package checks do not constitute full GPU/model or production acceptance. This unified distribution is a development build; confirm your intended workflow before production use.

## License

MATRIX LAB code remains subject to LICENSE. Bundled Cascadia Mono has its own license in web/assets/CascadiaMono-LICENSE.txt. External model weights and provider services retain their respective licenses and terms.
