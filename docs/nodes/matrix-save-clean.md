# MATRIX METADATA KILLER

Class ID: `MATRIX_SaveClean`

Category: `MATRIX LAB/Input & Output`

Saves every input image as JPEG or PNG without accepting prompt or workflow metadata. It is an output node and has no output sockets.

- Required: `images` (`IMAGE`)
- Options: `filename_prefix` (default `MATRIX`), `format` (`JPEG` or `PNG`, default `JPEG`), `quality` (1–100, default `100`)

JPEG uses fixed 4:4:4 chroma sampling. PNG is lossless. Container output is validated before atomic publication. This node does not remove information already burned into visible pixels.
