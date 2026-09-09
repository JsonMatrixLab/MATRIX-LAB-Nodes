# Installation for people

Install MATRIX LAB NODES package version 0.3.1 as one ComfyUI custom-node pack.

## Before you begin

- Use a working ComfyUI installation with Python 3.10 or newer.
- Back up important workflows and the current custom-node installation.
- Close ComfyUI before changing custom nodes.
- Check for folders that provide the older `MATRIXLAB-Nodes` or `MATRIXLAB-UI-Nodes` packs. They cannot remain enabled beside this unified package because class IDs overlap.
- Preserve the host's working Python, Torch, and CUDA versions.

## Install from Git

From the `custom_nodes` directory of the intended ComfyUI installation:

```bash
git clone https://github.com/JsonMatrixLab/MATRIX-LAB-Nodes.git matrix-lab-nodes
cd matrix-lab-nodes
```

If the repository is private, authenticate through your normal Git credential flow. Do not put a token in the clone URL, command history, or repository files.

Use the Python interpreter that launches this ComfyUI instance to install the declared dependencies. Review the command before running it if your environment manager might replace Torch:

```bash
python -m pip install -r requirements.txt
```

For portable or embedded ComfyUI, replace `python` with that installation's bundled interpreter and adjust the relative path.

## Install from an archive

Extract the release archive to a new folder named `matrix-lab-nodes` directly under the intended ComfyUI `custom_nodes` directory. The package root must contain `__init__.py`, `MANIFEST.json`, `requirements.txt`, `_core/`, `nodes/`, and `web/`. Avoid an extra archive wrapper directory.

## Restart and verify

1. Start ComfyUI through its normal launcher and inspect startup output for import errors.
2. Open node search and find `MATRIX RESOLUTION`, `MATRIX PHOTO FINISHER`, and `MATRIX AUTO PROMPTER`.
3. Compare the installed classes with `MANIFEST.json`. The menu should retain six `MATRIX LAB` category groups.
4. Add `MATRIX_Resolution`, select `3:4` and `2K`, and confirm outputs of 1536 by 2048 without queueing a model workflow.
5. Open a copy of an existing workflow and follow [docs/migration.md](docs/migration.md) if ComfyUI reports missing retired or incompatible classes.

This verification proves discovery and the local geometry path only. It does not prove every model, detector, sampler, GPU, or frontend renderer.

## External models and prompting

Model weights are not bundled. Installing the pack does not acquire them, establish redistribution rights, or complete compatible inference-runtime setup. `MATRIX_SkinMask` and `MATRIX_EyeMask` fail when their registered assets or compatible runtimes are unavailable; do not bypass identity checks with a similarly named file. A successful package import is not proof that either mask node is ready to execute. Follow [the detector and segmentation setup guide](docs/detector-setup.md) for exact paths, hashes, source evidence, runtime boundaries, and unresolved license questions.

`MATRIX_AutoPrompter` returns saved text during normal execution. Its explicit **Generate Prompt** control uses xAI and may incur charges. Configure credentials through its masked control or the documented server environment, never inside a workflow. Make the first provider call only after reviewing the selected model, reference images, request text, and cost boundary.

## Update

Back up workflows, record the installed commit or archive hash, and read [CHANGELOG.md](CHANGELOG.md) plus [docs/migration.md](docs/migration.md). Stop ComfyUI before updating. Do not merge a new archive over an existing tree; install the new version into a clean staging folder, verify its structure, then replace the disabled old folder using your normal recoverable file-management process.

After restart, repeat node discovery and test copies of important workflows. Keep the previous package available as a disabled rollback until those checks pass.

## Uninstall

Stop ComfyUI, back up any files you need, and remove or move the single `matrix-lab-nodes` folder through your normal recoverable process. Restart ComfyUI and confirm its classes are absent. Removing the pack does not remove provider account data, external model weights, ComfyUI input/output images, or saved workflows.
