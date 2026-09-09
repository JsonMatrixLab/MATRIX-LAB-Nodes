# MATRIX METADATA KILLER

Class ID: `MATRIX_MetadataKiller`

Category: `MATRIX LAB/Input & Output`

Save each image in a batch as a verified clean JPEG or PNG, with a small preview inside the node. Metadata Killer is an output node with one `IMAGE` input and no output sockets.

## Save controls

**Name** sets the filename prefix, initially `MATRIX`. Each saved image receives a numbered suffix. Use a plain filename prefix; directories, Windows reserved device names, forbidden filename characters and trailing dots or spaces are rejected. Concurrent saves select another available counter instead of overwriting an existing output.

**Export** selects the format and JPEG quality:

| Choice | Saved original |
| --- | --- |
| JPEG · High quality | JPEG at quality 95 |
| JPEG · Smaller file | JPEG at quality 85 |
| PNG · Lossless | PNG; JPEG quality does not affect it |
| JPEG · Custom | JPEG with an editable quality from 1 to 100 |

The stored defaults remain JPEG and quality 100, represented as custom quality. Editing custom quality does not switch the control to a preset, even when the value reaches 85 or 95. PNG keeps the stored JPEG quality for later use. Linked format or quality inputs remain authoritative; conflicting convenience controls are disabled while linked.

Existing workflows and API prompts keep the same save parameters: required `images`; optional `filename_prefix` (default `MATRIX`), `format` (`JPEG` or `PNG`, default `JPEG`), and `quality` (integer 1–100, default 100). Export is a convenience control over these values, not an additional saved input.

## Preview and original files

The contained preview preserves aspect ratio and uses a temporary WebP at up to 1,024 pixels on its longer edge. It represents the saved original and does not change the original file. Use batch navigation to inspect other saved images. The previous preview remains visible while the selected one loads.

**Open original** opens the full-resolution file in a dialog. **Download original** downloads that original file, not the small preview. The dialog has its own close control. The filename and metadata-verification status refer to the saved original.

If a preview cannot load, the original remains saved. **Retry preview** retries image loading without executing the workflow or saving another file. Temporary previews may expire; workflow reopening alone does not guarantee restoration of earlier execution images.

## Image and privacy behavior

JPEG uses fixed 4:4:4 chroma sampling. PNG preserves the quantized eight-bit pixels, including RGBA alpha. JPEG cannot preserve alpha and refuses RGBA input with a message directing you to PNG; it does not silently flatten transparency. Finite floating-point grayscale, RGB and supported PNG RGBA batches retain their dimensions. Empty or invalid images are rejected.

Every original is encoded fresh and checked for container metadata before publication. Prompt, workflow, EXIF, XMP, ICC and application metadata are not copied into the output. The node does not remove information already burned into visible pixels.

Files are published one at a time. If saving a later batch image fails or is interrupted, earlier verified files remain available and the error reports their count and filenames. Optional preview failure does not turn a successfully saved original into a failed save.
