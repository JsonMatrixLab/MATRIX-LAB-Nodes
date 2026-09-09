# MATRIX CROP TAIL PASTE

Class ID: `MATRIX_CropTailPaste`

Category: `MATRIX LAB/Sampling & Detail`

Runs a masked latent tail at crop scale and pastes the processed region back into the source image.

- Required sockets: `image`, `mask`, `model`, `noise`, `positive`, `vae`
- Main options: `guide_size` (default `1024`), `padding_px` (`64`), `start_sigma` (`0.22`), `steps` (`3`), `sampler_name` (`euler_ancestral`), `scheduler` (`beta57`), `feather_px` (`12`), `color_match` (`false`), `mask_mode` (`legacy_grow_feather`)
- Output: `image` (`IMAGE`)

It is suited to small regions such as eyes. A disconnected multi-person mask may form one bounding crop per frame. Validate mask coverage and the selected model/VAE path before relying on the result.
