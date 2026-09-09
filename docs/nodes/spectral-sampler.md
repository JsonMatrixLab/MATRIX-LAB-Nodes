# MATRIX SPECTRAL SAMPLER

Class ID: `MATRIXSpectralSampler`

Category: `MATRIX LAB/Sampling & Detail`

Provides a ComfyUI `SAMPLER`. `base_sampler` defaults to `euler`; its choices follow the sampler names available in the supported host ComfyUI contract. Native passthrough is obtained with a single scale of `1.0`.

Spectral controls include `transform` (`dwt` by default), `mode` (`delta_optimal`), `model_preset` (`custom`), `scales` (`0.5,1.0`), `delta` (`0.01`), `manual_sigmas` (`0.85`), spectrum parameters, and `spectral_seed` (`1088164640`).

The output is `sampler` (`SAMPLER`). Progressive behavior depends on the chosen solver and workflow; the node does not establish model training or native 4K support.
