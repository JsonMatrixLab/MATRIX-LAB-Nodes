"""Compiled declaration for MATRIX_CameraLook; regenerate instead of hand-editing."""
from __future__ import annotations

from ..._core.flow_utility import execute_compiled_node

NODE_ID = 'MATRIX_CameraLook'
OPERATION_BLOCK = 'color.camera-look'
SCHEMA_WIDGETS = {
    'image': ('IMAGE', {'forceInput': True}),
    'enabled': ('BOOLEAN', {'default': True}),
    'chromatic_aberration': ('FLOAT', {'default': 0.35, 'min': 0.0, 'max': 10.0}),
    'demosaic_pixel_blur': ('BOOLEAN', {'default': True}),
    'noise_strength': ('FLOAT', {'default': 1.9, 'min': 0.0, 'max': 5.0}),
    'kernel_motion_blur': ('INT', {'default': 1, 'min': 1, 'max': 51}),
    'jpeg_compression': ('INT', {'default': 98, 'min': 85, 'max': 100}),
    'look_seed': ('INT', {'default': 0, 'min': 0, 'max': 18446744073709551615}),
}
IMAGE_UPLOAD_FIELDS = ()
INPUT_SOCKET_TYPES = {'image': 'IMAGE', 'enabled': 'BOOLEAN', 'chromatic_aberration': 'FLOAT', 'demosaic_pixel_blur': 'BOOLEAN', 'noise_strength': 'FLOAT', 'kernel_motion_blur': 'INT', 'jpeg_compression': 'INT', 'look_seed': 'INT'}
REQUIRED_INPUT_NAMES = ('image',)
OUTPUT_SOCKET_TYPES = ('IMAGE',)
BATCH_POLICY = 'exactly-one'
INPUT_IS_LIST = False
OUTPUT_IS_LIST = (False,)
ROUTE_FIELD_NAMES = tuple(SCHEMA_WIDGETS)
FRAMEWORK_FIELD_NAMES = ()
# Socket labels whose values carry a leading batch dimension.
_BATCHED_SOCKETS = ('IMAGE', 'MASK', 'LATENT')

def _fill_widget_defaults(inputs):
    # An API prompt exported before a widget existed omits it; fall back to the declared
    # default instead of failing with KeyError (pod prompt 65e19bc3, sam_erosion_px, 2026-09-03).
    filled = dict(inputs)
    for name, spec in SCHEMA_WIDGETS.items():
        if name in filled or name in REQUIRED_INPUT_NAMES:
            continue
        options = spec[1] if isinstance(spec, (list, tuple)) and len(spec) > 1 and isinstance(spec[1], dict) else None
        if options is not None and 'default' in options:
            filled[name] = options['default']
    return filled

def _adapt_image_inputs(inputs):
    # Core VAE decoders can emit tiny finite excursions. Normalize them once at
    # the generated node boundary before strict operation contracts run.
    import logging
    try:
        import torch
    except ImportError:
        return inputs
    adapted = dict(inputs)
    for name, socket in INPUT_SOCKET_TYPES.items():
        if socket == 'IMAGE' and name in adapted:
            value = adapted[name]
            # Upload-backed IMAGE widgets carry a filename until their operation adapter.
            if not isinstance(value, torch.Tensor):
                continue
            if not bool(torch.isfinite(value).all().item()):
                raise ValueError('IMAGE contract violation: all values must be finite')
            minimum = value.amin().item()
            maximum = value.amax().item()
            if minimum < 0.0 or maximum > 1.0:
                if minimum < -0.02 or maximum > 1.02:
                    raise ValueError(
                        f'IMAGE contract violation: values must be in 0..1, received range {minimum}..{maximum}'
                    )
                logging.getLogger(__name__).info(
                    'Clamping IMAGE adapter input range %s..%s to 0..1', minimum, maximum
                )
                adapted[name] = value.clamp(0.0, 1.0)
    return adapted

def _input_widget(name):
    widget = SCHEMA_WIDGETS[name]
    if name not in IMAGE_UPLOAD_FIELDS:
        return widget
    import os
    import folder_paths
    input_dir = folder_paths.get_input_directory()
    files = [
        entry for entry in os.listdir(input_dir)
        if os.path.isfile(os.path.join(input_dir, entry))
    ]
    filter_types = getattr(folder_paths, 'filter_files_content_types', None)
    if callable(filter_types):
        files = filter_types(files, ['image'])
    else:
        image_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff')
        files = [entry for entry in files if entry.casefold().endswith(image_extensions)]
    options = dict(widget[1])
    options.pop('default', None)
    options['image_upload'] = True
    return (sorted(files), options)

def _payload_items(inputs):
    values = {
        name: inputs[name] for name in INPUT_SOCKET_TYPES if name in inputs
    }
    if not INPUT_IS_LIST:
        # A ComfyUI LIST is the engine calling the node once per item; a ComfyUI BATCH
        # is [B,H,W,C] inside one tensor. They are different axes, and `map` means the
        # batch one when the input is not a list. flow.api's own contract says
        # payload_items are 'compiler-separated' and that no block may infer items from
        # an IMAGE tensor — so the separation happens here. Measured 2026-07-29, prompt
        # 44ae97c4: eight frames arrived as one payload item and the operation refused.
        if BATCH_POLICY != 'map':
            return (values,)
        counts = {
            name: int(value.shape[0])
            for name, socket in INPUT_SOCKET_TYPES.items()
            for value in (values[name],)
            if socket in _BATCHED_SOCKETS and hasattr(value, 'shape')
        }
        if not counts:
            return (values,)
        sizes = set(counts.values())
        if len(sizes) != 1:
            raise ValueError(
                'batched inputs must agree on frame count, got ' + repr(counts)
            )
        count = sizes.pop()
        if count < 1:
            raise ValueError('a batched input must carry at least one frame')
        return tuple(
            {
                name: (
                    values[name][index:index + 1]
                    if name in counts
                    else values[name]
                )
                for name in INPUT_SOCKET_TYPES
            }
            for index in range(count)
        )
    if any(not isinstance(value, (list, tuple)) for value in values.values()):
        raise ValueError('utility list inputs must be list or tuple values')
    lengths = {len(value) for value in values.values()}
    if len(lengths) != 1:
        raise ValueError('utility list inputs must have equal lengths')
    count = lengths.pop() if lengths else 0
    if count < 1:
        raise ValueError('utility list inputs must not be empty')
    return tuple(
        {name: values[name][index] for name in INPUT_SOCKET_TYPES}
        for index in range(count)
    )

class MATRIXCameraLook:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                'image': _input_widget('image'),
            },
            "optional": {
                'enabled': _input_widget('enabled'),
                'chromatic_aberration': _input_widget('chromatic_aberration'),
                'demosaic_pixel_blur': _input_widget('demosaic_pixel_blur'),
                'noise_strength': _input_widget('noise_strength'),
                'kernel_motion_blur': _input_widget('kernel_motion_blur'),
                'jpeg_compression': _input_widget('jpeg_compression'),
                'look_seed': _input_widget('look_seed'),
            },
        }

    RETURN_TYPES = ('IMAGE',)
    RETURN_NAMES = ('image',)
    FUNCTION = "execute"
    CATEGORY = 'MATRIX LAB/Image Processing'
    DESCRIPTION = 'Generated from operation block color.camera-look.'
    INPUT_IS_LIST = INPUT_IS_LIST
    OUTPUT_IS_LIST = OUTPUT_IS_LIST

    async def execute(self, **inputs):
        inputs = _adapt_image_inputs(_fill_widget_defaults(inputs))
        from ..._core import color_camera_look as _operation_block
        inputs['__flow_runtime__'] = {
            'resolved_blocks': {OPERATION_BLOCK: _operation_block},
            'input_socket_types': INPUT_SOCKET_TYPES,
            'required_input_names': REQUIRED_INPUT_NAMES,
            'output_socket_types': OUTPUT_SOCKET_TYPES,
            'batch_policy': BATCH_POLICY,
            'payload_items': _payload_items(inputs),
            'input_is_list': INPUT_IS_LIST,
            'output_is_list': OUTPUT_IS_LIST,
        }
        return await execute_compiled_node(NODE_ID, '', '', inputs)

NODE_CLASS_MAPPINGS = {NODE_ID: MATRIXCameraLook}
NODE_DISPLAY_NAME_MAPPINGS = {NODE_ID: 'MATRIX CAMERA LOOK'}
