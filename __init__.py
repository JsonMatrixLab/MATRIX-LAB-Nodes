"""Compiled ComfyUI node pack."""
from .nodes.matrixspectralsampler import NODE_CLASS_MAPPINGS as _c0, NODE_DISPLAY_NAME_MAPPINGS as _d0
from .nodes.matrix_latenttail import NODE_CLASS_MAPPINGS as _c1, NODE_DISPLAY_NAME_MAPPINGS as _d1
from .nodes.matrix_skinmask import NODE_CLASS_MAPPINGS as _c2, NODE_DISPLAY_NAME_MAPPINGS as _d2
from .nodes.matrix_eyemask import NODE_CLASS_MAPPINGS as _c3, NODE_DISPLAY_NAME_MAPPINGS as _d3
from .nodes.matrix_croptailpaste import NODE_CLASS_MAPPINGS as _c4, NODE_DISPLAY_NAME_MAPPINGS as _d4
from .nodes.matrix_saveclean import NODE_CLASS_MAPPINGS as _c5, NODE_DISPLAY_NAME_MAPPINGS as _d5
from .nodes.matrix_outputstage import NODE_CLASS_MAPPINGS as _c6, NODE_DISPLAY_NAME_MAPPINGS as _d6
from .nodes.matrix_renoise import NODE_CLASS_MAPPINGS as _c7, NODE_DISPLAY_NAME_MAPPINGS as _d7
from .nodes.matrix_cameralook import NODE_CLASS_MAPPINGS as _c8, NODE_DISPLAY_NAME_MAPPINGS as _d8
from .nodes.matrixlab_resolution import NODE_CLASS_MAPPINGS as _c9, NODE_DISPLAY_NAME_MAPPINGS as _d9
from .nodes.matrixlab_aiinfluencerresolution import NODE_CLASS_MAPPINGS as _c10, NODE_DISPLAY_NAME_MAPPINGS as _d10
from .nodes.matrixlab_easycrop import NODE_CLASS_MAPPINGS as _c11, NODE_DISPLAY_NAME_MAPPINGS as _d11
from .nodes.matrixlab_imagebatchloader import NODE_CLASS_MAPPINGS as _c12, NODE_DISPLAY_NAME_MAPPINGS as _d12

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
NODE_CLASS_MAPPINGS.update(_c12)
NODE_DISPLAY_NAME_MAPPINGS.update(_d12)

try:
    import folder_paths as _matrix_folder_paths
except ImportError:
    _matrix_folder_paths = None
if _matrix_folder_paths is not None:
    from ._core.runtime_bootstrap import bootstrap_runtime as _bootstrap_runtime
    _bootstrap_runtime()

WEB_DIRECTORY = "./web"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

from ._core.prompt_director import MATRIXLAB_PromptDirector
NODE_CLASS_MAPPINGS['MATRIXLAB_PromptDirector'] = MATRIXLAB_PromptDirector
NODE_DISPLAY_NAME_MAPPINGS['MATRIXLAB_PromptDirector'] = 'MATRIX Auto Prompter'
from ._core.prompt_director.server_routes import register_routes as _register_prompt_director
_register_prompt_director()

MATRIXLAB_PromptDirector.CATEGORY = 'MATRIX LAB/Prompting'
