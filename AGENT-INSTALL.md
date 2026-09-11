# Installation contract for AI agents

Install the exact operator-authorized MATRIX LAB NODES package version 0.4.0 as one
ComfyUI custom-node pack. Treat the installed `MANIFEST.json` as the exact class
inventory and reject artifacts whose manifest does not declare version `0.4.0`.

## Hard boundaries

- Resolve the intended ComfyUI root from the launcher or operator configuration; never guess from a common path.
- Do not overwrite, merge, delete, move, or replace an existing installation without explicit operator approval.
- An existing target is acceptable only when its recorded source/hash and manifest
  match the exact operator-authorized 0.4.0 artifact. Refuse enabled legacy packs
  that register overlapping class IDs.
- Treat `matrix-krea2-adapter`, the older `MATRIXLAB-Nodes` and
  `MATRIXLAB-UI-Nodes` split packs, and a standalone Metadata Killer as explicit
  collision candidates. Preserve them and disable or replace them recoverably only
  with the operator's case-specific authority.
- Do not change ComfyUI core or replace a working host Python, Torch, or CUDA environment.
- Do not read, print, copy, log, commit, create, rotate, or alter credential values.
- Do not enable or queue the xAI **Generate Prompt** action, a paid provider operation, or a model workflow during installation verification.
- Do not claim success from files or imports alone. Verify discovery in the visible ComfyUI UI.

## Procedure

1. Resolve and report the exact ComfyUI root, its launcher, and the Python interpreter used by that launcher.
2. Stop ComfyUI through its normal controlled process.
3. Inspect `custom_nodes` for the target, `matrix-krea2-adapter`, the older
   `MATRIXLAB-Nodes` and `MATRIXLAB-UI-Nodes` split packs, and any standalone
   Metadata Killer. Report exact folders and preserve them. If the target already
   exists, record its source/hash and read its manifest. Continue in place only if it
   is the exact authorized 0.4.0 artifact. Any disable or replacement requires the
   operator's case-specific authority and a recoverable rollback.
4. Obtain the exact operator-authorized 0.4.0 commit or release archive. If GitHub requests access,
   use an authenticated repository source or an owner-supplied archive. Record the
   commit SHA or SHA-256 before installation.
5. If the exact artifact is not already installed, place it in a new direct child
   folder `custom_nodes/matrix-lab-nodes` after resolving any approved replacement.
   Refuse archive traversal, an extra wrapper directory, symlink or junction
   surprises, or files outside that folder.
6. Verify that the root contains `__init__.py`, `MANIFEST.json`, `requirements.txt`,
   `_core/`, `nodes/`, and `web/`. Read `MANIFEST.json`; require `pack_id`
   `matrix-lab-nodes`, version `0.4.0`, 20 unique class IDs, and six category groups.
   The IDs must resolve to 16 current nodes plus the four aliases listed in
   `NODES.md`. Do not infer the
   inventory from filenames or an older manifest.
7. Resolve the declared Python dependencies with the same interpreter that runs ComfyUI. Preserve an already working Torch/CUDA stack. If dependency resolution would replace Torch, CUDA packages, or another host-critical package, stop and present the proposed changes.
8. Restart ComfyUI through its normal launcher. Treat any pack import or frontend asset error as failure.
9. Confirm from startup records and live node metadata that all 20 IDs resolve to the
   unified `matrix-lab-nodes` folder. Stop if any provider or frontend asset resolves
   to `matrix-krea2-adapter`, an older split pack, or the standalone Metadata Killer.
10. In the visible UI, load separate copies of a legacy-ID workflow and a current-ID
    workflow. Verify green MATRIX controls for both IDs in each pair: Spectral
    Sampler, AI Influencer Resolution 2K/4K, Image Batch Loader, and Auto Prompter.
    Do not save, migrate, or otherwise alter either workflow.
11. Add `MATRIX_Resolution`, choose `3:4` and `2K`, and verify 1536 by 2048. Do not
    queue any model, detector, sampler, provider path, or paid action.
12. Report the installed source/hash, target folder, manifest version and all 20
    providers, dependency actions, paired-ID visible results, geometry result, and
    every blocker. Distinguish offline checks from unperformed live renderer, GPU,
    model, and workflow acceptance.

## Credential and private-data boundary

The Auto Prompter credential must be supplied only by the operator through the masked node control or server environment. Never inspect an existing provider key or test it during installation. Do not upload images, prompts, workflows, logs, or screenshots. Diagnostics must exclude credentials, local paths, private media, prompt text, and provider response bodies.
