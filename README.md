# MATRIX LAB NODES

MATRIX LAB NODES (package version 0.2.0) is a unified ComfyUI custom-node pack for image input, resolution planning, sampling, masks, finishing, output, and assisted prompting.

> [!IMPORTANT]
> Version 0.2.0 is a development candidate. Offline package and ABI checks do not establish full live acceptance across ComfyUI renderers, GPU/model combinations, or production workflows.

The package keeps fourteen classes in six stable menu groups under `MATRIX LAB`. The exact classes in a downloaded build are also listed in its `MANIFEST.json`.

## What it does

- Loads and crops ordered input images without silently resizing mixed dimensions.
- Calculates model-independent 1K, 2K, and 4K pixel geometry.
- Supplies sampling and masked detail helpers for ComfyUI workflows.
- Builds skin and eye masks through separately supplied, identity-checked model assets.
- Applies deterministic local photo finishing and saves clean JPEG or PNG output.
- Returns a saved prompt locally; an explicit **Generate Prompt** action can call xAI after credential setup and paid-use approval.

## Included groups

| Group | Included nodes |
| --- | --- |
| [Input & Output](nodes/input_output/) | MATRIX METADATA KILLER, MATRIX IMAGE BATCH LOADER |
| [Resolution & Layout](nodes/resolution_layout/) | MATRIX RESOLUTION, MATRIX AI INFLUENCER RESOLUTION, MATRIX AI INFLUENCER RESOLUTION 2K/4K |
| [Sampling & Detail](nodes/sampling_detail/) | MATRIX SPECTRAL SAMPLER, MATRIX LATENT TAIL, MATRIX CROP TAIL PASTE |
| [Masks & Detection](nodes/masks_detection/) | MATRIX SKIN MASK, MATRIX EYE MASK |
| [Image Processing](nodes/image_processing/) | MATRIX PHOTO FINISHER, MATRIX EASY CROP, MATRIX OUTPUT STAGE |
| [Prompting](nodes/prompting/) | MATRIX AUTO PROMPTER |

See [NODES.md](NODES.md) for the class inventory and [the node guides](docs/nodes/) for inputs, outputs, and practical boundaries.

## Install

- For a normal installation, follow [INSTALL.md](INSTALL.md).
- For installation by a zero-context coding agent, provide the repository and require [AGENT-INSTALL.md](AGENT-INSTALL.md).

Do not install this pack beside the older `MATRIXLAB-Nodes` or `MATRIXLAB-UI-Nodes` packs. Shared class IDs would register twice. Back up workflows and the previous installation, disable the old packs, install this package as one folder under `custom_nodes`, restart ComfyUI, and confirm the expected classes in node search before opening an important workflow.

## Safe start

1. Read the installed `MANIFEST.json` and confirm the class inventory.
2. Add `MATRIXLAB_Resolution` and verify its two integer outputs.
3. Load a copy of one workflow and resolve missing or changed classes using [the migration guide](docs/migration.md).
4. Keep **Generate Prompt** unused until an xAI credential, model choice, and paid request are intentionally approved.

For a local image-processing check, load [the Photo Finisher example](examples/README.md), choose your own PNG or JPEG, and preview the result. The example contains no photograph, model weights, or provider call.

## Dependencies and data

The pack uses the Python/Torch environment supplied by ComfyUI and declares Pillow, aiohttp, NumPy, SciPy, and Torch. Preserve a working host Torch/CUDA installation when resolving dependencies. Detection nodes need external model assets and compatible inference runtimes; model acquisition, licensing, and compatible runtime setup are not completed by installing this repository. Model weights are not bundled. Their hashes and logical identities are checked by the runtime registry, but this package does not grant rights to those files. The mask nodes are not ready to run merely because the pack imports.

Most nodes run locally. `MATRIXLAB_PromptDirector` performs no network request during ordinary graph execution. Its explicit **Generate Prompt** action sends the selected local reference images and prompt fields to xAI. Credentials stay outside serialized workflows. Provider use may incur charges and remains subject to the provider's terms.

## Release boundary

The repository is the source distribution channel. A GitHub Release, Comfy Registry entry, or ComfyUI Manager listing is a separate publication and must not be inferred from repository availability. Compatibility evidence and current limits are documented in [docs/compatibility.md](docs/compatibility.md).

## License and security

MATRIX LAB code remains subject to [LICENSE](LICENSE). Bundled Cascadia Mono is covered separately in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). Read [SECURITY.md](SECURITY.md) before sharing diagnostics that may contain private workflow or provider data.
