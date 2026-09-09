"""Prompting registration; shared service implementation stays in the core."""
from ..._core.prompt_director import MATRIX_AutoPrompter as _PromptDirector


class MATRIX_AutoPrompter(_PromptDirector):
    CATEGORY = 'MATRIX LAB/Prompting'
