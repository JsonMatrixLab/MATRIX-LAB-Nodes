"""Visible terminal states for LLM completions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TerminalCompletion:
    """Text plus the terminal state the node must expose."""

    text: str
    finish_state: str


class TextRefusal(RuntimeError):
    """The provider returned a refusal as a successful HTTP response."""

    error_class = "refusal"


class EmptyCompletion(RuntimeError):
    """A terminal success did not contain completion text."""

    error_class = "empty_or_malformed_success"


class UnknownFinishState(RuntimeError):
    """The transport did not normalize a terminal provider state."""

    error_class = "empty_or_malformed_success"


class ContextLengthExceeded(RuntimeError):
    """The selected context window cannot fit the requested generation."""

    error_class = "context_length"

    def __init__(
        self,
        *,
        model: str,
        model_limit: int,
        input_tokens: int,
        output_allowance: int,
        truncation_policy: str,
    ) -> None:
        self.model = model
        self.model_limit = model_limit
        self.input_tokens = input_tokens
        self.output_allowance = output_allowance
        self.truncation_policy = truncation_policy
        super().__init__(
            f"{model} context limit {model_limit} tokens cannot fit "
            f"input={input_tokens} + output_allowance={output_allowance}; "
            f"truncation={truncation_policy}."
        )


def finish_completion(
    *,
    text: str,
    finish_state: str,
    model: str,
    detail: str = "",
    model_limit: int | None = None,
    input_tokens: int | None = None,
    output_allowance: int | None = None,
    truncation_policy: str = "disabled",
) -> TerminalCompletion:
    """Return terminal completion state or raise its visible failure class."""
    if finish_state == "refusal":
        raise TextRefusal(detail or f"{model} refused the request.")
    if finish_state == "context_length":
        if None in (model_limit, input_tokens, output_allowance):
            raise ValueError(
                "context_length requires model_limit, input_tokens, and output_allowance"
            )
        raise ContextLengthExceeded(
            model=model,
            model_limit=model_limit,
            input_tokens=input_tokens,
            output_allowance=output_allowance,
            truncation_policy=truncation_policy,
        )
    if finish_state == "complete" and not text:
        raise EmptyCompletion(f"{model} returned an empty completed response.")
    if finish_state not in {"complete", "partial"}:
        raise UnknownFinishState(
            f"{model} returned unsupported finish state {finish_state!r}."
        )
    return TerminalCompletion(text=text, finish_state=finish_state)


__all__ = [
    "ContextLengthExceeded",
    "EmptyCompletion",
    "TerminalCompletion",
    "TextRefusal",
    "UnknownFinishState",
    "finish_completion",
]
