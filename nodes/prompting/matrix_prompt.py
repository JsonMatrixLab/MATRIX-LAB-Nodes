"""One canonical multiline STRING widget and one verbatim STRING output."""
from comfy_api.latest import io

from ..._core.text_prompt import verbatim_prompt


class MATRIXPrompt(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MATRIX_Prompt",
            display_name="MATRIX PROMPT",
            category="MATRIX LAB/Prompting",
            description="Preserve an editable multiline prompt exactly as entered.",
            inputs=[io.String.Input("prompt", default="", multiline=True)],
            outputs=[io.String.Output("prompt")],
        )

    @classmethod
    def execute(cls, prompt: str) -> io.NodeOutput:
        return io.NodeOutput(verbatim_prompt(prompt))


NODE_CLASS_MAPPINGS = {"MATRIX_Prompt": MATRIXPrompt}
NODE_DISPLAY_NAME_MAPPINGS = {"MATRIX_Prompt": "MATRIX PROMPT"}
