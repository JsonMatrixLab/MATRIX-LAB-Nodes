"""MATRIX Auto Prompter node and explicit paid server service."""

from __future__ import annotations

SYSTEM_PROMPT = "Analyze all ordered reference images jointly with the user's instructions and return one coherent English visual-generation prompt. Describe subject identity, pose, framing, scene, wardrobe, lighting, and natural skin texture. Return only the prompt. Do not add commentary or unsupported weights. Follow the exact character-trigger instruction supplied with the request; do not invent or alter trigger tokens."
DEFAULT_MODEL = "grok-4.20-0309-non-reasoning"
EMPTY_GENERATION_STATE = '{"version":1,"state":"idle","request_id":null}'
DEFAULT_INSTRUCTIONS = "Create one coherent photorealistic Krea 2 prompt from these references."


class MATRIXLAB_PromptDirector:
    @classmethod
    def INPUT_TYPES(cls):
        fields = {
            "instructions": ("STRING", {"default": DEFAULT_INSTRUCTIONS, "multiline": True}),
            "system_prompt": ("STRING", {"default": SYSTEM_PROMPT, "multiline": True}),
            "model": ("STRING", {"default": DEFAULT_MODEL}),
            "final_prompt": ("STRING", {"default": "", "multiline": True}),
            "generation_state": ("STRING", {"default": EMPTY_GENERATION_STATE}),
            "character_trigger": ("STRING", {"default": ""}),
        }
        optional = {"images": ("IMAGE", {"forceInput": True, "lazy": True})}
        return {"required": fields, "optional": optional}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "execute"
    CATEGORY = "MATRIX LAB UI NODES/Prompting"
    DESCRIPTION = "Explicitly generate once, edit the saved prompt, then reuse it for free."

    def check_lazy_status(self, **_inputs):
        # References belong to the explicit button request. Normal graph execution must
        # never wake an empty/upstream loader merely to return already saved text.
        return []

    def execute(
        self,
        instructions="",
        system_prompt="",
        model="",
        final_prompt="",
        generation_state="idle",
        character_trigger="",
        **_images,
    ):
        if not isinstance(final_prompt, str) or not final_prompt.strip():
            raise ValueError("Generate or enter a final prompt before running the workflow.")
        return (final_prompt,)


from .server_routes import PromptDirectorService, load_model_configs, register_routes

__all__ = ["DEFAULT_INSTRUCTIONS", "DEFAULT_MODEL", "EMPTY_GENERATION_STATE", "MATRIXLAB_PromptDirector", "PromptDirectorService", "SYSTEM_PROMPT", "load_model_configs", "register_routes"]
