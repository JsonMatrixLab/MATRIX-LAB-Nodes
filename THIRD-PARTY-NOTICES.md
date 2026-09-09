# Third-party notices

## Cascadia Mono

This distribution includes `web/assets/CascadiaMono.woff2`. The font is licensed under the SIL Open Font License, Version 1.1. The bundled license text is available at `web/assets/CascadiaMono-LICENSE.txt` and controls use of that font.

## Items not bundled

Python dependencies are installed separately into the user's ComfyUI environment. External detector, segmentation, and other model weights are not included.

The optional mask runtimes can involve ONNX Runtime, Ultralytics, and Segment Anything. Segment Anything publishes Apache-2.0 terms. Ultralytics publishes AGPL-3.0 and Enterprise options; which terms apply to this proprietary pack and a particular deployment has not been established here. Consult current upstream terms before installing, integrating, or distributing these packages.

The four expected detector and segmentation weights, their source links, hashes, and available license evidence are listed in [docs/detector-setup.md](docs/detector-setup.md). The Eye Mask detector weight has no established license in the retained evidence; the human-parts weight's underlying model license and the U-2-Net conversion lineage also remain unresolved. Review each source and intended use independently. Provider services and other downloaded assets have their own terms. This notice does not add rights to third-party code, weights, or services.
