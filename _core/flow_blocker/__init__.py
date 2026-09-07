"""Blocked output slots for ComfyUI graph orchestration."""


class BlockerReasonError(ValueError):
    """The blocker reason cannot become a user-visible message."""


class OfflineExecutionBlocker:
    """Message-compatible stand-in when ComfyUI is not importable."""

    def __init__(self, message: str):
        self.message = message


def blocked_output(reason: str) -> object:
    """Return one filled output-slot value that blocks its consumers."""

    if not isinstance(reason, str):
        raise BlockerReasonError("blocker reason must be a non-empty string")
    if not reason.strip():
        raise BlockerReasonError("blocker reason must be a non-empty string")

    try:
        from comfy_execution.graph import ExecutionBlocker
    except ImportError:
        return OfflineExecutionBlocker(reason)
    return ExecutionBlocker(reason)


def is_blocked_output(value: object) -> bool:
    """Return whether orchestration must propagate ``value`` without consuming it."""

    if isinstance(value, OfflineExecutionBlocker):
        return True
    try:
        from comfy_execution.graph import ExecutionBlocker
    except ImportError:
        return False
    return isinstance(value, ExecutionBlocker)


__all__ = [
    "BlockerReasonError",
    "OfflineExecutionBlocker",
    "blocked_output",
    "is_blocked_output",
]
