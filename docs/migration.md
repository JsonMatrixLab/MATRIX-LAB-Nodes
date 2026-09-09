# Migration to the unified package

Version 0.2.0 replaces two older packs with one package. Back up workflows and the existing installations before switching. The older `MATRIXLAB-Nodes` and `MATRIXLAB-UI-Nodes` packs must remain disabled while this package is enabled because retained class IDs otherwise register twice.

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

`MATRIXLAB_Resolution` now returns only `width` and `height`. Its canonical controls are `aspect_ratio`, `resolution_tier`, `custom_width`, and `custom_height`. A former `max_side` or `divisible_by` value cannot be copied by widget position. Recreate the node and reconnect outputs by name and meaning.

`MATRIXLAB_AIInfluencerResolution` also returns only `width` and `height`. Older saved versions exposed six render, delivery, sampler-scale, and plan outputs. Replace those nodes manually and review every downstream link because output indices no longer share the same meaning. The current `1K` choice means an exact 1024-pixel longer edge.

`MATRIX_ResolutionPlan`, `MATRIXLAB_Resolution2K`, and `MATRIXLAB_Resolution4KProgressive` are not included. Workflows using them require deliberate replacement. `MATRIXLAB_AIInfluencerResolution2K4K` is a two-output geometry selector and is not an ABI-compatible substitute for the older connected model/sampler nodes.

Current Krea 2 graphs that still contain `MATRIX_CameraLook` or `MATRIX_Renoise` are not drop-in compatible with this package. Migrate those graphs manually before treating the unified pack as their replacement.

## Retained class IDs

Other base classes retain their class IDs, but widget schemas and runtime assets must still be checked against [NODES.md](../NODES.md) and the installed manifest. Open a copy of each important workflow, inspect missing nodes and shifted widgets, save, reload, and verify links before running model-dependent paths.

## Rollback reference

The legacy predecessor revision is `eaa50a674005b4e7bf7be13f0c289faeb37bfcef`. Keep the old installation disabled and intact until migrated workflows pass. Restore that exact revision as a separate rollback operation; do not copy shared `_core`, `nodes`, or `web` folders between versions.
