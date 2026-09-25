# MATRIX H3 RESOLUTION

This additive geometry utility exposes exactly four canonical widgets in this order: `aspect_ratio`, `resolution_tier`, `custom_width`, and `custom_height`. It returns exactly two `INT` outputs named `width` and `height`.

The preset tiers use 1024- and 2048-pixel long edges, with dimensions divisible by 32.

| Aspect | 1K width x height | 2K width x height |
|---|---|---|
| 1:1 | 1024 x 1024 | 2048 x 2048 |
| 16:9 | 1024 x 576 | 2048 x 1152 |
| 9:16 | 576 x 1024 | 1152 x 2048 |
| 4:3 | 1024 x 768 | 2048 x 1536 |
| 3:4 | 768 x 1024 | 1536 x 2048 |

Custom width and height are the actual generation pixels; each must be an integer from 32 through 2048 and a multiple of 32. The tier does not override Custom. Connect the two outputs to the generator's width and height inputs; keep delivery resizing in a separate stage.

The node performs no model inference, model selection, image transform, upscale, crop, or delivery-size calculation.

The H3 controls and saved state were tested with ComfyUI 0.37.0 and frontend 1.53.6 in Classic and Nodes 2.0, including invalid Custom values and reset. This node-level check does not certify other nodes or every model/resolution combination. Larger generation sizes require separate memory and inference qualification.

## Migrating the V0.6 prototype

The V0.6 H3 prototype serialized five widgets, including `sizing_mode`, and exposed five outputs with generation/output/4x meanings. Old graphs must be migrated by replacing the node and reconnecting every output by meaning. The frontend refuses that five-widget serialization by changing its node type to an explicit migration-required sentinel before configuration; it never shifts the old positional values into the four-widget interface.
