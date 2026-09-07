"""Prompting registration; shared service implementation stays in the core."""
from ..._core.prompt_director import MATRIXLAB_PromptDirector as _PromptDirector


class MATRIXLAB_PromptDirector(_PromptDirector):
    CATEGORY = 'MATRIX LAB/Prompting'
