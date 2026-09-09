# MATRIX AUTO PROMPTER

Class ID: `MATRIXLAB_PromptDirector`

Category: `MATRIX LAB/Prompting`

Returns the editable saved `final_prompt` as `prompt` (`STRING`). Ordinary graph execution performs no I/O and makes no provider request.

The optional `images` input accepts saved local references from MATRIX IMAGE BATCH LOADER or a compatible native Load Image path. The node stores instructions, system prompt, selected model, final prompt, generation state, and character trigger as its visible execution state.

The explicit **Generate Prompt** action can send one to ten ordered local images and the prompt fields to xAI. It requires a valid credential, supported model, and literal paid-use authorization. The masked credential stays outside workflow serialization. Failed, uncertain, or repeated requests fail closed rather than silently resubmitting. Review images and text before using the action; provider charges and terms may apply.
