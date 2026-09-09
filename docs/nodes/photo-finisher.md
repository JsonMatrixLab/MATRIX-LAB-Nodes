# MATRIX PHOTO FINISHER

Class ID: `MATRIX_PhotoFinisher`

Category: `MATRIX LAB/Image Processing`

Applies deterministic, display-referred photographic finishing while preserving image shape, batch order, device, dtype, and alpha. It runs locally with Torch and makes no network request.

## Profiles

Profiles set the starting balance; the controls below trim that profile.

| Profile | Character |
| --- | --- |
| `Clean Digital` | The lightest texture and neutral color, with a modest crisp detail base. |
| `Everyday Capture` | A balanced default with mild contrast and warmth, restrained saturation, and moderate texture. |
| `Low Light` | Softer detail and contrast with the warmest, strongest, broadest texture of the three profiles. |

These are creative calibrations for display-referred images. They are not measured camera, sensor, RAW, or ISO simulations.

## Controls

| Input | Range and default | Meaning |
| --- | --- | --- |
| `image` | Required `IMAGE` | Finite RGB or RGBA BHWC tensor in `[0,1]`, using fp16, fp32, or bf16. |
| `mask` | Optional `MASK` | Application weight: `0` preserves source pixels and `1` applies the selected `mix`. Soft values blend proportionally. |
| `profile` | Three choices; `Everyday Capture` | Selects the base tone, color, detail, and texture calibration. |
| `mix` | `0..1`; `1` | Blends the complete finished result with the source. Zero returns the original image unchanged. |
| `texture` | `0..2`; `1` | Scales the profile's deterministic luminance and chroma texture. Zero disables texture. |
| `detail` | `-1..1`; `1` | Trims profile detail. Negative values reduce detail and can soften; positive values sharpen. |
| `contrast` | `-1..1`; `0` | Adds or reduces contrast around the profile's base contrast. |
| `warmth` | `-1..1`; `0` | Shifts midtones warmer or cooler around the profile's base warmth. |
| `saturation` | `0..2`; `1` | Multiplies the profile's chroma. Zero produces grayscale. |
| `seed` | `0..4294967295`; `42` | Fixes coordinate-based texture. It does not change after generation automatically. |

The output is one `IMAGE`. New nodes start with `Everyday Capture`, mix `1`, texture `1`, detail `1`, contrast `0`, warmth `0`, saturation `1`, and seed `42`.

## Mask and image rules

The mask must be floating-point BHW data in `[0,1]` with exactly the same height and width as the image. Its batch must be one, which broadcasts across the image batch, or equal the image batch for framewise masks. The node never resizes or guesses a mask. An all-zero mask returns the original image unchanged; exact-zero pixels remain exact source pixels.

RGB and RGBA inputs retain their exact shape. Alpha is copied unchanged. The operation does not resize, crop, compress, edit metadata, mutate inputs, or use global random state. Invalid ranks, channels, dimensions, batches, dtypes, nonfinite values, or out-of-range values fail before a result is returned.

Try the local, provider-free [Photo Finisher example](../../examples/photo-finisher.json) with your own PNG or JPEG input.
