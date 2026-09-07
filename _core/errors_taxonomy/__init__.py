"""Named provider failures, classified by the user's next safe action."""

import re


class ProviderFailure(RuntimeError):
    kind = ""
    retryable = False

    def __init__(
        self,
        message,
        *,
        status=None,
        provider_code=None,
        task_id=None,
        billability="none",
    ):
        super().__init__(message)
        self.user_message = str(message)
        self.status = status
        self.provider_code = provider_code
        self.task_id = task_id
        self.billability = billability


class LocalValidationError(ProviderFailure):
    kind = "local_validation"


class AuthError(ProviderFailure):
    kind = "auth"


class InsufficientFundsOrQuotaError(ProviderFailure):
    kind = "insufficient_funds_or_quota"


class ModerationError(ProviderFailure):
    kind = "moderation"


class RateLimitError(ProviderFailure):
    kind = "rate_limit"
    retryable = True


class TransientTransportOrServerError(ProviderFailure):
    kind = "transient_transport_or_server"
    retryable = True


class PermanentProviderRejectionError(ProviderFailure):
    kind = "permanent_provider_rejection"


class EmptyOrMalformedSuccessError(ProviderFailure):
    kind = "empty_or_malformed_success"


class IndeterminateSubmitError(ProviderFailure):
    kind = "indeterminate_submit"

    def __init__(
        self,
        message,
        *,
        record=None,
        billability="possibly_billed",
        **context,
    ):
        super().__init__(message, billability=billability, **context)
        self.record = dict(record or {})


class TimeoutOrInterruptedError(ProviderFailure):
    kind = "timeout_or_interrupted"

    def __init__(self, message, *, reason="unspecified", **context):
        super().__init__(message, **context)
        self.reason = reason


class ContextLengthError(ProviderFailure):
    kind = "context_length"


ERROR_TYPES = {
    error_type.kind: error_type
    for error_type in (
        LocalValidationError,
        AuthError,
        InsufficientFundsOrQuotaError,
        ModerationError,
        RateLimitError,
        TransientTransportOrServerError,
        PermanentProviderRejectionError,
        EmptyOrMalformedSuccessError,
        IndeterminateSubmitError,
        TimeoutOrInterruptedError,
        ContextLengthError,
    )
}


def _redact_detail(detail):
    text = str(detail)[:1000]
    text = re.sub(r"https?://\S+", "[redacted URL]", text, flags=re.IGNORECASE)
    text = re.sub(
        r"(?i)\b(authorization|api[_-]?key|token|secret)\b\s*[:=]\s*(?:bearer\s+)?\S+",
        r"\1: [redacted]",
        text,
    )
    return text[:300]


def failure_from_http(status, detail="", **context):
    """Return the failure matching an HTTP rejection; callers raise the result."""
    text = str(detail)
    lowered = text.lower()
    if status == 402 or any(
        marker in lowered
        for marker in ("insufficient fund", "quota exceed", "billing", "payment required")
    ):
        error_type = InsufficientFundsOrQuotaError
    elif any(marker in lowered for marker in ("moderat", "safety", "nsfw", "content policy")):
        error_type = ModerationError
    elif any(
        marker in lowered
        for marker in ("context length", "context window", "too many tokens", "token limit")
    ):
        error_type = ContextLengthError
    elif status in (401, 403):
        error_type = AuthError
    elif status == 429:
        error_type = RateLimitError
    elif status == 408 or status >= 500:
        error_type = TransientTransportOrServerError
    else:
        error_type = PermanentProviderRejectionError
    return error_type(
        _redact_detail(text) or f"provider HTTP {status}",
        status=status,
        **context,
    )


def raise_failure(kind, message, **context):
    """Raise a named failure; provider failures never become socket values."""
    raise ERROR_TYPES[kind](message, **context)
