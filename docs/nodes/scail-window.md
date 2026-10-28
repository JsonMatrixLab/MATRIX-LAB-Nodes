# MATRIX SCAIL WINDOW ENGINE

`MATRIX_SCAILWindow` runs SCAIL-2 motion generation for an exact requested duration. It uses ComfyUI core's native SCAIL conditioning, sampler, and VAE decode paths, then joins decoded windows into one `IMAGE` batch.

## Inputs and output

Connect `MODEL`, positive and negative `CONDITIONING`, `VAE`, pose video and its colored mask, a reference image and its colored mask, and `frame_count`. Width and height must be multiples of 32. Sampling controls are `seed`, `steps`, `cfg`, `denoise`, `sampler_name`, and `scheduler`; SCAIL controls are `pose_strength`, `pose_start`, `pose_end`, `replacement_mode`, and optional `clip_vision_output`.

The sole output is `images: IMAGE`, containing exactly `frame_count` decoded frames.

## Window contract

The first generation window is 81 frames. Continuations retain five decoded frames as context and advance by 76 new frames, giving the fixed 81/5/76 contract. Pose and mask tails are held together when alignment or the final continuation needs extra coverage, and the decoded result is trimmed to exact N.

The node returns stitched decoded images, not a stitched `LATENT`. It validates counts, geometry, paired image/mask shapes, finite image ranges, sampler values, and native offsets. `frame_count`, width, and height are each limited to 16384; width and height have a minimum of 32 and a step of 32.

## Prerequisites and verification

Use a SCAIL-2 model and the SCAIL support supplied by ComfyUI core. Model weights are not bundled by this pack.

Offline node, window, distribution, JavaScript, and install-readback tests pass for this build. Renderer Classic / Nodes 2.0 live acceptance and GPU execution of this exact unified build are **NOT TESTED**.
