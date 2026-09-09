# Migration to 0.3.0

Version 0.3.0 deliberately standardizes eight class IDs. It still contains fourteen registered nodes in six categories. The old IDs are not registered as aliases, so existing workflow JSON must be migrated before those nodes can load.

## Class ID mapping

| 0.2.0 class ID | 0.3.0 class ID |
| --- | --- |
| `MATRIX_SaveClean` | `MATRIX_MetadataKiller` |
| `MATRIXLAB_PromptDirector` | `MATRIX_AutoPrompter` |
| `MATRIXLAB_ImageBatchLoader` | `MATRIX_ImageBatchLoader` |
| `MATRIXLAB_Resolution` | `MATRIX_Resolution` |
| `MATRIXLAB_AIInfluencerResolution` | `MATRIX_AIInfluencerResolution` |
| `MATRIXLAB_AIInfluencerResolution2K4K` | `MATRIX_AIInfluencerResolution2K4K` |
| `MATRIXLAB_EasyCrop` | `MATRIX_EasyCrop` |
| `MATRIXSpectralSampler` | `MATRIX_SpectralSampler` |

## Safe offline migration

Back up workflows before switching packages. Run the repository tool offline and write to a new output file:

```bash
python tools/migrate_workflow.py --input old.json --output new.json
```

Keep `old.json` unchanged. Do not use the same path for input and output, overwrite an existing migration result, or batch-replace arbitrary strings by hand. The tool duplicates the workflow and rewrites only the eight class IDs in the table. Open `new.json` in ComfyUI, inspect every migrated node and connection, then save and reload before execution.

The older `MATRIXLAB-Nodes` and `MATRIXLAB-UI-Nodes` packs must remain disabled while version 0.3.0 is enabled because overlapping historical installations can register conflicting classes.

## Finishing-node replacement

`MATRIX_CameraLook` and `MATRIX_Renoise` are retired. Replace their chain with `MATRIX_PhotoFinisher`, reconnect the IMAGE path, and tune the result from the new defaults:

- profile: `Everyday Capture`
- mix: `1`
- texture: `1`
- detail: `1`
- contrast: `0`
- warmth: `0`
- saturation: `1`
- seed: `42`

There is no exact mapping for the old ISO, JPEG, or motion controls. Photo Finisher applies creative, display-referred tone, color, detail, and texture; it does not reproduce camera sensor, RAW, ISO, demosaic, motion-blur, chromatic-fringe, or JPEG behavior. Existing workflows that reference either retired class load it as missing until it is replaced manually.

## Resolution changes

`MATRIX_Resolution` returns only `width` and `height`. Its canonical controls are `aspect_ratio`, `resolution_tier`, `custom_width`, and `custom_height`. A former `max_side` or `divisible_by` value cannot be copied by widget position. Recreate the node and reconnect outputs by name and meaning.

`MATRIX_AIInfluencerResolution` also returns only `width` and `height`. Older saved versions exposed six render, delivery, sampler-scale, and plan outputs. Replace those nodes manually and review every downstream link because output indices no longer share the same meaning. The current `1K` choice means an exact 1024-pixel longer edge.

`MATRIX_ResolutionPlan`, `MATRIXLAB_Resolution2K`, and `MATRIXLAB_Resolution4KProgressive` are not included. Workflows using them require deliberate replacement. `MATRIX_AIInfluencerResolution2K4K` is a two-output geometry selector and is not an ABI-compatible substitute for the older connected model/sampler nodes.

Current Krea 2 graphs that still contain `MATRIX_CameraLook` or `MATRIX_Renoise` are not drop-in compatible with this package. The offline tool does not rewrite either class because replacing them requires a semantic decision. Replace them manually with `MATRIX_PhotoFinisher`, reconnect the image path, and retune the finish before treating the unified pack as their replacement.

## Retained class IDs

Other base classes retain their class IDs, but widget schemas and runtime assets must still be checked against [NODES.md](../NODES.md) and the installed manifest. Open a copy of each important workflow, inspect missing nodes and shifted widgets, save, reload, and verify links before running model-dependent paths.

## Rollback reference

For the pre-rename 0.2.0 package, use tag `legacy-class-ids-0.2.0-2026-09-09` at revision `0e798eac7d6569ad183ce0a036b81e63f0d7304e`.

The older Camera Look/Renoise predecessor is preserved by tag `legacy-camera-renoise-2026-09-09`. Its revision is `eaa50a674005b4e7bf7be13f0c289faeb37bfcef`. Keep the old installation disabled and intact until migrated workflows pass. Restore that exact revision as a separate rollback operation; do not copy shared `_core`, `nodes`, or `web` folders between versions.
