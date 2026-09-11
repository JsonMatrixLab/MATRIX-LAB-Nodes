# Krea2 FP8 GPU guards

These optional nodes contain observed corruption of resident Krea2 normalization
and modulation parameters during repeated GPU execution. They preserve native
normalization and modulation mathematics; they do not identify or repair the
original writer of corrupted memory.

## Wiring

- Replace the Krea2 CLIP loader with `MATRIX_Krea2CLIPLoader`, selecting the native
  Qwen3-VL 4B Krea2 text encoder. Connect its CLIP output to text encoding.
- Connect the FP8 diffusion loader to `MATRIX_Krea2ModelGuard`, then connect its
  MODEL output to the diffusion LoRA loader. Install the guard before LoRAs.
- Keep ordinary compatible diffusion linear LoRAs. Patches to protected parameters,
  incompatible hooks and encoder LoRA patches are rejected rather than ignored.

The CLIP guard retains independent CPU copies of native RMSNorm weights. The model
node creates and caches a native static CUDA delegate before capturing independent
normalization and modulation references. Native calculations still run on CUDA;
CPU reference storage is not CPU text encoding. Static model creation may require
another checkpoint load and additional temporary host memory. References are scoped
to model instances, not globally registered buffers or global class overrides.

## Evidence and limits

The exact 0.4.0 package and release workflow completed 2K with Photo Finisher ON,
2K with it OFF, and 4K with it ON on an RTX 5090. All runs used the standard manual
prompt, no LoRA, and no optional provider request. The same Classic session verified
all 20 unified registrations, then saved the workflow and loaded it in a fresh
browser with exact frontend/API graph equality.

FP8 diffusion is the accepted scope. INT8 is not supported by this acceptance.
The observed runtime used ComfyUI 0.33.3 at core
`4da9e2dbead52fc1e68beae33fe3d7ad63b63241`, frontend 1.49.6, and PyTorch
2.8.0+cu128. New runtime versions or different patches require validation. Nodes 2.0
is not supported or verified for this release. Offline tests exercise native-shaped
module and patcher doubles, including corruption containment, invalid patch
rejection, static delegate reuse and reference integrity; they are not GPU tests.

The separate empty-SAM-mask behavior change is included in the V1-compatible
package; it is independent of these two guards.
No NaN replacement, clipping of invalid predictions, lower LoRA strength or CPU
encoding is used to turn a failed calculation into an apparent success.
