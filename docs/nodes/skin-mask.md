# MATRIX SKIN MASK

Class ID: `MATRIX_SkinMask`

Category: `MATRIX LAB/Masks & Detection`

Builds a skin-region mask from selected human-part classes, with an optional person-silhouette gate.

- Required: `image` (`IMAGE`)
- Options: `face`, `torso`, `arms`, `legs` (all default `true`), `feather_px` (`16`), `edge_radius_px` (`8`), `expand_px` (`4`), `person_gate` (`true`)
- Outputs: `mask` (`MASK`), `preview` (`IMAGE`)

Selected regions cover every represented person; this is still-image batch processing without identity tracking. Turning all four part switches off returns an empty mask without inference. Other runs require separately configured segmentation assets and runtimes. Missing configuration fails instead of downloading or guessing a model. Complete [detector and segmentation setup](../detector-setup.md) before testing a nonempty selection.
