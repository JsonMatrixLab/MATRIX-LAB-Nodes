# MATRIX OUTPUT STAGE

Class ID: `MATRIX_OutputStage`

Category: `MATRIX LAB/Image Processing`

Resolves an image toward explicit target dimensions through the connected model, noise, conditioning, and VAE path, with optional model upscaling.

- Required: `image`, `model`, `noise`, `positive`, `vae`, `target_width`, `target_height`
- Options: `upscale_model`, `sigma_base` (default `0.15`), `sigma_per_octave` (`0.1`), `steps` (`3`), `sampler_name` (`res_multistep`), `scheduler` (`beta57`), `resize_method` (`lanczos`), `decode_tile` (`512`), `decode_overlap` (`64`)
- Outputs: `image` (`IMAGE`), `info` (`STRING`)

The accepted behavior includes shrink-or-pass use. Quality, memory use, and supported dimensions depend on the connected model, VAE, optional upscale model, and host hardware; this node does not certify them.
