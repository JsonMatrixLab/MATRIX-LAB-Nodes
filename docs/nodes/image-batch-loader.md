# MATRIX IMAGE BATCH LOADER

Class ID: `MATRIXLAB_ImageBatchLoader`

Category: `MATRIX LAB/Input & Output`

Loads an ordered collection of one to ten static JPEG or PNG files from ComfyUI input storage. Dragging, removal, and reorder operations update one canonical `collection` value. The selected tile controls preview only; execution processes every item in order.

- Required: `collection` (`STRING`, managed by the gallery)
- Outputs: `images` (`IMAGE` list), `masks` (`MASK` list)

Each image retains its own dimensions. The node does not stack, pad, crop, or resize mixed sizes. EXIF orientation is applied; alpha becomes the matching ComfyUI mask. Empty collections, duplicates, traversal paths, animated images, malformed state, or missing files fail closed.
