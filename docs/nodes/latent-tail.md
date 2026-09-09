# MATRIX LATENT TAIL

Class ID: `MATRIX_LatentTail`

Category: `MATRIX LAB/Sampling & Detail`

Runs a short tail sampling pass on a latent, optionally limited by a mask.

- Required sockets: `model` (`MODEL`), `noise` (`NOISE`), `positive` (`CONDITIONING`), `latent` (`LATENT`)
- Options: `start_sigma` (default `0.26`), `steps` (`3`), `sampler_name` (`euler_ancestral`), `scheduler` (`beta57`), optional `mask`
- Output: `latent` (`LATENT`)

The node is a compact replacement for wiring the equivalent scheduler, noise-mask, guider, and advanced sampler tail manually. Its result still depends on compatible model, conditioning, noise, sampler, scheduler, and latent inputs.
