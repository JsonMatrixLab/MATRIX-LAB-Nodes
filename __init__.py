"""Compiled ComfyUI node pack."""
from .nodes.sampling_detail.matrix_spectralsampler import NODE_CLASS_MAPPINGS as _c0, NODE_DISPLAY_NAME_MAPPINGS as _d0
from .nodes.sampling_detail.matrix_latenttail import NODE_CLASS_MAPPINGS as _c1, NODE_DISPLAY_NAME_MAPPINGS as _d1
from .nodes.masks_detection.matrix_skinmask import NODE_CLASS_MAPPINGS as _c2, NODE_DISPLAY_NAME_MAPPINGS as _d2
from .nodes.masks_detection.matrix_eyemask import NODE_CLASS_MAPPINGS as _c3, NODE_DISPLAY_NAME_MAPPINGS as _d3
from .nodes.sampling_detail.matrix_croptailpaste import NODE_CLASS_MAPPINGS as _c4, NODE_DISPLAY_NAME_MAPPINGS as _d4
from .nodes.input_output.matrix_metadatakiller import NODE_CLASS_MAPPINGS as _c5, NODE_DISPLAY_NAME_MAPPINGS as _d5
from .nodes.image_processing.matrix_outputstage import NODE_CLASS_MAPPINGS as _c6, NODE_DISPLAY_NAME_MAPPINGS as _d6
from .nodes.image_processing.matrix_photofinisher import NODE_CLASS_MAPPINGS as _c7, NODE_DISPLAY_NAME_MAPPINGS as _d7
from .nodes.resolution_layout.matrix_resolution import NODE_CLASS_MAPPINGS as _c8, NODE_DISPLAY_NAME_MAPPINGS as _d8
from .nodes.resolution_layout.matrix_aiinfluencerresolution import NODE_CLASS_MAPPINGS as _c9, NODE_DISPLAY_NAME_MAPPINGS as _d9
from .nodes.image_processing.matrix_easycrop import NODE_CLASS_MAPPINGS as _c10, NODE_DISPLAY_NAME_MAPPINGS as _d10
from .nodes.input_output.matrix_imagebatchloader import NODE_CLASS_MAPPINGS as _c11, NODE_DISPLAY_NAME_MAPPINGS as _d11

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
NODE_CLASS_MAPPINGS.update(_c0)
NODE_DISPLAY_NAME_MAPPINGS.update(_d0)
NODE_CLASS_MAPPINGS.update(_c1)
NODE_DISPLAY_NAME_MAPPINGS.update(_d1)
NODE_CLASS_MAPPINGS.update(_c2)
NODE_DISPLAY_NAME_MAPPINGS.update(_d2)
NODE_CLASS_MAPPINGS.update(_c3)
NODE_DISPLAY_NAME_MAPPINGS.update(_d3)
NODE_CLASS_MAPPINGS.update(_c4)
NODE_DISPLAY_NAME_MAPPINGS.update(_d4)
NODE_CLASS_MAPPINGS.update(_c5)
NODE_DISPLAY_NAME_MAPPINGS.update(_d5)
NODE_CLASS_MAPPINGS.update(_c6)
NODE_DISPLAY_NAME_MAPPINGS.update(_d6)
NODE_CLASS_MAPPINGS.update(_c7)
NODE_DISPLAY_NAME_MAPPINGS.update(_d7)
NODE_CLASS_MAPPINGS.update(_c8)
NODE_DISPLAY_NAME_MAPPINGS.update(_d8)
NODE_CLASS_MAPPINGS.update(_c9)
NODE_DISPLAY_NAME_MAPPINGS.update(_d9)
NODE_CLASS_MAPPINGS.update(_c10)
NODE_DISPLAY_NAME_MAPPINGS.update(_d10)
NODE_CLASS_MAPPINGS.update(_c11)
NODE_DISPLAY_NAME_MAPPINGS.update(_d11)

from .nodes.resolution_layout.matrix_aiinfluencerresolution2k4k import NODE_CLASS_MAPPINGS as _resolution_2k4k_c, NODE_DISPLAY_NAME_MAPPINGS as _resolution_2k4k_d
NODE_CLASS_MAPPINGS.update(_resolution_2k4k_c)
NODE_DISPLAY_NAME_MAPPINGS.update(_resolution_2k4k_d)

try:
    import folder_paths as _matrix_folder_paths
except ImportError:
    _matrix_folder_paths = None
if _matrix_folder_paths is not None:
    from ._core.runtime_bootstrap import bootstrap_runtime as _bootstrap_runtime
    _bootstrap_runtime()

WEB_DIRECTORY = "./web"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

from .nodes.prompting.matrix_autoprompter import MATRIX_AutoPrompter
NODE_CLASS_MAPPINGS['MATRIX_AutoPrompter'] = MATRIX_AutoPrompter
NODE_DISPLAY_NAME_MAPPINGS['MATRIX_AutoPrompter'] = 'MATRIX AUTO PROMPTER'
from ._core.prompt_director.server_routes import register_routes as _register_prompt_director
_register_prompt_director()

# BEGIN generated Krea2 GPU guards
from .krea2_clip_loader import NODE_CLASS_MAPPINGS as _gpu_krea2_clip_loader_c, NODE_DISPLAY_NAME_MAPPINGS as _gpu_krea2_clip_loader_d
NODE_CLASS_MAPPINGS.update(_gpu_krea2_clip_loader_c)
NODE_DISPLAY_NAME_MAPPINGS.update(_gpu_krea2_clip_loader_d)
from .krea2_model_guard import NODE_CLASS_MAPPINGS as _gpu_krea2_model_guard_c, NODE_DISPLAY_NAME_MAPPINGS as _gpu_krea2_model_guard_d
NODE_CLASS_MAPPINGS.update(_gpu_krea2_model_guard_c)
NODE_DISPLAY_NAME_MAPPINGS.update(_gpu_krea2_model_guard_d)
# END generated Krea2 GPU guards

# BEGIN Krea2 V1 compatibility
from .nodes.image_processing.matrix_cameralook import NODE_CLASS_MAPPINGS as _matrix_cameralook_c, NODE_DISPLAY_NAME_MAPPINGS as _matrix_cameralook_d
NODE_CLASS_MAPPINGS.update(_matrix_cameralook_c)
NODE_DISPLAY_NAME_MAPPINGS.update(_matrix_cameralook_d)
from .nodes.image_processing.matrix_renoise import NODE_CLASS_MAPPINGS as _matrix_renoise_c, NODE_DISPLAY_NAME_MAPPINGS as _matrix_renoise_d
NODE_CLASS_MAPPINGS.update(_matrix_renoise_c)
NODE_DISPLAY_NAME_MAPPINGS.update(_matrix_renoise_d)
NODE_CLASS_MAPPINGS['MATRIXSpectralSampler'] = type('MATRIXSpectralSampler', (NODE_CLASS_MAPPINGS['MATRIX_SpectralSampler'],), {"__module__": __name__})
NODE_DISPLAY_NAME_MAPPINGS['MATRIXSpectralSampler'] = NODE_DISPLAY_NAME_MAPPINGS['MATRIX_SpectralSampler']
NODE_CLASS_MAPPINGS['MATRIXLAB_AIInfluencerResolution2K4K'] = type('MATRIXLAB_AIInfluencerResolution2K4K', (NODE_CLASS_MAPPINGS['MATRIX_AIInfluencerResolution2K4K'],), {"__module__": __name__})
NODE_DISPLAY_NAME_MAPPINGS['MATRIXLAB_AIInfluencerResolution2K4K'] = NODE_DISPLAY_NAME_MAPPINGS['MATRIX_AIInfluencerResolution2K4K']
NODE_CLASS_MAPPINGS['MATRIXLAB_ImageBatchLoader'] = type('MATRIXLAB_ImageBatchLoader', (NODE_CLASS_MAPPINGS['MATRIX_ImageBatchLoader'],), {"__module__": __name__})
NODE_DISPLAY_NAME_MAPPINGS['MATRIXLAB_ImageBatchLoader'] = NODE_DISPLAY_NAME_MAPPINGS['MATRIX_ImageBatchLoader']
NODE_CLASS_MAPPINGS['MATRIXLAB_PromptDirector'] = type('MATRIXLAB_PromptDirector', (NODE_CLASS_MAPPINGS['MATRIX_AutoPrompter'],), {"__module__": __name__})
NODE_DISPLAY_NAME_MAPPINGS['MATRIXLAB_PromptDirector'] = NODE_DISPLAY_NAME_MAPPINGS['MATRIX_AutoPrompter']
# END Krea2 V1 compatibility
