"""Compiled declaration for MATRIX_CropTailPaste; regenerate instead of hand-editing."""
from __future__ import annotations

from .._core.flow_utility import execute_compiled_node

NODE_ID = 'MATRIX_CropTailPaste'
OPERATION_BLOCK = 'sample.crop-tail-paste'
SCHEMA_WIDGETS = {
    'image': ('IMAGE', {'forceInput': True}),
    'mask': ('MASK', {'forceInput': True}),
    'model': ('MODEL', {'forceInput': True}),
    'noise': ('NOISE', {'forceInput': True}),
    'positive': ('CONDITIONING', {'forceInput': True}),
    'vae': ('VAE', {'forceInput': True}),
    'guide_size': ('INT', {'default': 1024, 'min': 256, 'max': 2048, 'step': 16}),
    'padding_px': ('INT', {'default': 64, 'min': 0, 'max': 512}),
    'start_sigma': ('FLOAT', {'default': 0.22, 'min': 0.05, 'max': 0.6, 'step': 0.01}),
    'steps': ('INT', {'default': 3, 'min': 1, 'max': 12}),
    'sampler_name': (['euler', 'euler_cfg_pp', 'euler_ancestral', 'euler_ancestral_cfg_pp', 'heun', 'heunpp2', 'exp_heun_2_x0', 'exp_heun_2_x0_sde', 'dpm_2', 'dpm_2_ancestral', 'lms', 'dpm_fast', 'dpm_adaptive', 'dpmpp_2s_ancestral', 'dpmpp_2s_ancestral_cfg_pp', 'dpmpp_sde', 'dpmpp_sde_gpu', 'dpmpp_2m', 'dpmpp_2m_cfg_pp', 'dpmpp_2m_sde', 'dpmpp_2m_sde_gpu', 'dpmpp_2m_sde_heun', 'dpmpp_2m_sde_heun_gpu', 'dpmpp_3m_sde', 'dpmpp_3m_sde_gpu', 'ddpm', 'lcm', 'ipndm', 'ipndm_v', 'deis', 'res_multistep', 'res_multistep_cfg_pp', 'res_multistep_ancestral', 'res_multistep_ancestral_cfg_pp', 'gradient_estimation', 'gradient_estimation_cfg_pp', 'er_sde', 'seeds_2', 'seeds_3', 'sa_solver', 'sa_solver_pece', 'ddim', 'uni_pc', 'uni_pc_bh2'], {'default': 'euler_ancestral'}),
    'scheduler': (['beta57', 'simple', 'sgm_uniform', 'karras', 'exponential', 'ddim_uniform', 'beta', 'normal', 'linear_quadratic', 'kl_optimal'], {'default': 'beta57'}),
    'feather_px': ('INT', {'default': 12, 'min': 0, 'max': 64}),
    'color_match': ('BOOLEAN', {'default': False}),
}
IMAGE_UPLOAD_FIELDS = ()
INPUT_SOCKET_TYPES = {'image': 'IMAGE', 'mask': 'MASK', 'model': 'MODEL', 'noise': 'NOISE', 'positive': 'CONDITIONING', 'vae': 'VAE', 'guide_size': 'INT', 'padding_px': 'INT', 'start_sigma': 'FLOAT', 'steps': 'INT', 'sampler_name': 'STRING', 'scheduler': 'STRING', 'feather_px': 'INT', 'color_match': 'BOOLEAN'}
REQUIRED_INPUT_NAMES = ('image', 'mask', 'model', 'noise', 'positive', 'vae')
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

class MATRIXCropTailPaste:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                'image': _input_widget('image'),
                'mask': _input_widget('mask'),
                'model': _input_widget('model'),
                'noise': _input_widget('noise'),
                'positive': _input_widget('positive'),
                'vae': _input_widget('vae'),
            },
            "optional": {
                'guide_size': _input_widget('guide_size'),
                'padding_px': _input_widget('padding_px'),
                'start_sigma': _input_widget('start_sigma'),
                'steps': _input_widget('steps'),
                'sampler_name': _input_widget('sampler_name'),
                'scheduler': _input_widget('scheduler'),
                'feather_px': _input_widget('feather_px'),
                'color_match': _input_widget('color_match'),
            },
        }

    RETURN_TYPES = ('IMAGE',)
    RETURN_NAMES = ('image',)
    FUNCTION = "execute"
    CATEGORY = 'MATRIX LAB/Sampling & Detail'
    DESCRIPTION = 'Generated from operation block sample.crop-tail-paste.'
    INPUT_IS_LIST = INPUT_IS_LIST
    OUTPUT_IS_LIST = OUTPUT_IS_LIST

    async def execute(self, **inputs):
        inputs = _adapt_image_inputs(_fill_widget_defaults(inputs))
        from .._core import sample_crop_tail_paste as _operation_block
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

NODE_CLASS_MAPPINGS = {NODE_ID: MATRIXCropTailPaste}
NODE_DISPLAY_NAME_MAPPINGS = {NODE_ID: 'MATRIX Crop Tail Paste'}
