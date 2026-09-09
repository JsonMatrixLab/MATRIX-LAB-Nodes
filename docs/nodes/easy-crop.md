# MATRIX EASY CROP

Class ID: `MATRIX_EasyCrop`


Category: `MATRIX LAB/Image Processing`

Loads one static ComfyUI input image and returns the visible crop plus its alpha-derived mask.

- Required controls: `image`, `aspect_ratio` (`Free`, `1:1`, `16:9`, `9:16`, `Custom`), `custom_ratio_width`, `custom_ratio_height`, and normalized `crop_x`, `crop_y`, `crop_width`, `crop_height`
- Outputs: `image` (`IMAGE`), `mask` (`MASK`)

The backend applies EXIF orientation before crop geometry. RGB, grayscale, and RGBA images are accepted; animated images, malformed paths, invalid rectangles, and images above the declared size limit are rejected. Sources without alpha return a zero mask. The node does not modify the source file.
