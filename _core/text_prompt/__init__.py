"""Verbatim multiline prompt utility."""


def verbatim_prompt(prompt: str) -> str:
    """Return the exact string, including empty text, Unicode, and whitespace."""
    if not isinstance(prompt, str):
        raise TypeError("prompt must be a string")
    return prompt


__all__ = ["verbatim_prompt"]
