# MATRIX VIDEO METADATA KILLER

`MATRIX_VideoMetadataKiller` accepts ComfyUI's native `VIDEO` plus the existing
`filename_prefix` widget and writes a new MP4 without overwriting an existing file.
Its `VIDEO` output is a new `VideoFromFile` backed by that saved result, so downstream
nodes consume the cleaned file rather than the original input.

The node remuxes supported encoded video and audio streams without re-encoding them.
It removes descriptive container and stream tags, including workflow tags. It does
not remove visible watermarks, edit pixels/audio, or promise removal of codec-level
or indispensable playback structure. Only MP4 input is currently supported; an
unsupported container or codec fails without publishing a success file.
