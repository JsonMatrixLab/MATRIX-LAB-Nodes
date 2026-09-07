"""Compiled declaration for MATRIXLAB_EasyCrop; regenerate instead of hand-editing."""
from __future__ import annotations

from .._core.flow_utility import execute_compiled_node

NODE_ID = 'MATRIXLAB_EasyCrop'
OPERATION_BLOCK = 'easy.crop'
SCHEMA_WIDGETS = {
    'image': ('STRING', {'default': '', 'image_upload': True}),
    'aspect_ratio': (['Free', '1:1', '16:9', '9:16', 'Custom'], {'default': 'Free'}),
    'custom_ratio_width': ('INT', {'default': 1, 'min': 1, 'max': 1000, 'step': 1}),
    'custom_ratio_height': ('INT', {'default': 1, 'min': 1, 'max': 1000, 'step': 1}),
    'crop_x': ('FLOAT', {'default': 0.0, 'min': 0.0, 'max': 1.0, 'step': 1e-06}),
    'crop_y': ('FLOAT', {'default': 0.0, 'min': 0.0, 'max': 1.0, 'step': 1e-06}),
    'crop_width': ('FLOAT', {'default': 1.0, 'min': 1e-06, 'max': 1.0, 'step': 1e-06}),
    'crop_height': ('FLOAT', {'default': 1.0, 'min': 1e-06, 'max': 1.0, 'step': 1e-06}),
}
IMAGE_UPLOAD_FIELDS = ('image',)
INPUT_SOCKET_TYPES = {'image': 'STRING', 'aspect_ratio': 'STRING', 'custom_ratio_width': 'INT', 'custom_ratio_height': 'INT', 'crop_x': 'FLOAT', 'crop_y': 'FLOAT', 'crop_width': 'FLOAT', 'crop_height': 'FLOAT'}
REQUIRED_INPUT_NAMES = ('image', 'aspect_ratio', 'custom_ratio_width', 'custom_ratio_height', 'crop_x', 'crop_y', 'crop_width', 'crop_height')
OUTPUT_SOCKET_TYPES = ('IMAGE', 'MASK')
BATCH_POLICY = 'exactly-one'
INPUT_IS_LIST = False
OUTPUT_IS_LIST = (False, False)
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

class MATRIXLABEasyCrop:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                'image': _input_widget('image'),
                'aspect_ratio': _input_widget('aspect_ratio'),
                'custom_ratio_width': _input_widget('custom_ratio_width'),
                'custom_ratio_height': _input_widget('custom_ratio_height'),
                'crop_x': _input_widget('crop_x'),
                'crop_y': _input_widget('crop_y'),
                'crop_width': _input_widget('crop_width'),
                'crop_height': _input_widget('crop_height'),
            },
            "optional": {
            },
        }

    RETURN_TYPES = ('IMAGE', 'MASK')
    RETURN_NAMES = ('image', 'mask')
    FUNCTION = "execute"
    CATEGORY = 'MATRIX LAB/Image Processing'
    DESCRIPTION = 'Generated from operation block easy.crop.'
    INPUT_IS_LIST = INPUT_IS_LIST
    OUTPUT_IS_LIST = OUTPUT_IS_LIST

    @classmethod
    def VALIDATE_INPUTS(cls, **inputs):
        from .._core import easy_crop as _operation_block
        return _operation_block.validate_image_input(
            inputs.get(IMAGE_UPLOAD_FIELDS[0])
        )

    @classmethod
    def IS_CHANGED(cls, **inputs):
        from .._core import easy_crop as _operation_block
        return _operation_block.input_digest(
            inputs.get(IMAGE_UPLOAD_FIELDS[0])
        )

    async def execute(self, **inputs):
        inputs = _adapt_image_inputs(_fill_widget_defaults(inputs))
        from .._core import easy_crop as _operation_block
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

NODE_CLASS_MAPPINGS = {NODE_ID: MATRIXLABEasyCrop}
NODE_DISPLAY_NAME_MAPPINGS = {NODE_ID: 'MATRIX Easy Crop'}
